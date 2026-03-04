# Requirements Document

## Introduction

The Knowledge Graph (KG) concept resolution pipeline has two quality gaps that prevent relevant document chunks from surfacing in RAG query results. First, the concept extraction phase during document processing fails to recognize code-specific terms (snake_case identifiers, camelCase, API parameters, function calls) because the NER patterns in `ConceptExtractor` only match proper nouns, gerunds, and abstract nouns. Second, the query-time retrieval phase suffers from reranking dilution: relationship traversal fans out to hundreds of loosely related chunks, and the semantic reranker has no mechanism to prioritize direct-concept chunks (hop_distance=0) over distant traversal chunks (hop_distance=1,2), causing correct results to be lost in noise.

This spec addresses both root causes to improve KG-based retrieval precision for technical and domain-specific queries.

## Glossary

- **ConceptExtractor**: The class in `kg_builder.py` responsible for extracting concepts from document text using regex-based NER patterns and storing them in the knowledge graph.
- **Concept_Pattern**: A regex pattern used by the ConceptExtractor to identify candidate concept terms in text.
- **Code_Term**: A technical identifier containing underscores, dots, camelCase, equals signs, or parentheses (e.g., `allow_dangerous_code`, `getData()`, `max_retries=3`).
- **KGRetrievalService**: The service in `kg_retrieval_service.py` that orchestrates two-stage KG-guided retrieval (Stage 1: KG candidate retrieval, Stage 2: semantic reranking).
- **SemanticReranker**: The component in `semantic_reranker.py` that reranks Stage 1 candidate chunks using a weighted combination of KG relevance scores and semantic similarity scores.
- **Hop_Distance**: The number of relationship edges traversed in the knowledge graph to reach a concept from the originally matched concept. Direct concept chunks have hop_distance=0.
- **Direct_Chunk**: A chunk retrieved from the `source_chunks` of a concept that directly matched the query (hop_distance=0).
- **Related_Chunk**: A chunk retrieved via relationship traversal from a related concept (hop_distance >= 1).
- **ChunkSourceMapping**: The data model that tracks provenance of each retrieved chunk, including its source concept, retrieval source, and hop distance.
- **Reranking_Dilution**: The phenomenon where a large number of loosely related chunks from relationship traversal overwhelm the reranker, causing highly relevant direct chunks to be ranked below less relevant traversal chunks.

## Requirements

### Requirement 1: Code-Specific Concept Extraction

**User Story:** As a user querying technical documents, I want code-specific terms (snake_case identifiers, API parameters, function calls) to be extracted as concepts during document processing, so that KG retrieval can match queries containing those terms.

#### Acceptance Criteria

1. WHEN the ConceptExtractor processes text containing snake_case identifiers (e.g., `allow_dangerous_code`, `max_retries`), THE ConceptExtractor SHALL extract each snake_case identifier as a concept.
2. WHEN the ConceptExtractor processes text containing camelCase or PascalCase identifiers (e.g., `getData`, `ConnectionManager`), THE ConceptExtractor SHALL extract each camelCase or PascalCase identifier as a concept.
3. WHEN the ConceptExtractor processes text containing parameter assignments (e.g., `allowed_dangerous_code=True`, `timeout=30`), THE ConceptExtractor SHALL extract the full parameter assignment as a concept.
4. WHEN the ConceptExtractor processes text containing function or method calls (e.g., `process_document()`, `getData()`), THE ConceptExtractor SHALL extract the function or method name as a concept.
5. WHEN the ConceptExtractor processes text containing dotted identifiers (e.g., `os.path.join`, `config.settings`), THE ConceptExtractor SHALL extract the dotted identifier as a concept.
6. WHEN a code term concept is extracted, THE ConceptExtractor SHALL store the concept with a category label of `CODE_TERM` to distinguish code concepts from natural language concepts.
7. WHEN the ConceptExtractor encounters a code term that overlaps with an existing natural language concept pattern match, THE ConceptExtractor SHALL retain both the code term concept and the natural language concept as separate entries.

### Requirement 2: Hop-Distance-Aware KG Scoring

**User Story:** As a user querying the knowledge graph, I want chunks from directly matched concepts to be scored significantly higher than chunks found via multi-hop traversal, so that the most relevant results are not diluted by loosely related content.

#### Acceptance Criteria

1. WHEN the KGRetrievalService assigns a KG relevance score to a Direct_Chunk (hop_distance=0), THE KGRetrievalService SHALL assign a base KG relevance score of 1.0.
2. WHEN the KGRetrievalService assigns a KG relevance score to a Related_Chunk, THE KGRetrievalService SHALL reduce the score by a decay factor for each hop in the relationship path, using the formula `score = decay_factor ^ hop_distance` where `decay_factor` is configurable and defaults to 0.5.
3. WHEN the SemanticReranker calculates the final score for a chunk, THE SemanticReranker SHALL incorporate the hop-distance-based KG relevance score into the weighted scoring formula alongside the semantic similarity score.
4. WHEN two chunks have equal semantic similarity scores, THE SemanticReranker SHALL rank the chunk with the lower hop_distance higher.

### Requirement 3: Relationship Traversal Result Limiting

**User Story:** As a system operator, I want the KG retrieval pipeline to limit the number of chunks returned from relationship traversal, so that the reranker receives a manageable candidate set and direct-concept chunks are not overwhelmed.

#### Acceptance Criteria

1. WHEN the KGRetrievalService performs relationship traversal, THE KGRetrievalService SHALL limit the total number of Related_Chunks to a configurable maximum (default: 50 chunks).
2. WHEN the number of Related_Chunks exceeds the configured maximum, THE KGRetrievalService SHALL retain only the Related_Chunks with the lowest hop_distance values, breaking ties by concept match confidence.
3. WHEN Direct_Chunks are present in the candidate set, THE KGRetrievalService SHALL guarantee that all Direct_Chunks are included in the candidate set passed to the SemanticReranker, regardless of the traversal limit.

### Requirement 4: Existing Concept Extraction Backward Compatibility

**User Story:** As a system operator, I want the new code-term extraction patterns to coexist with existing NER patterns, so that previously extracted natural language concepts continue to be recognized without regression.

#### Acceptance Criteria

1. THE ConceptExtractor SHALL continue to extract proper noun concepts using the existing ENTITY patterns without modification.
2. THE ConceptExtractor SHALL continue to extract gerund concepts using the existing PROCESS patterns without modification.
3. THE ConceptExtractor SHALL continue to extract abstract noun concepts using the existing PROPERTY patterns without modification.
4. WHEN the ConceptExtractor processes text containing both code terms and natural language terms, THE ConceptExtractor SHALL extract concepts from all pattern categories (ENTITY, PROCESS, PROPERTY, and CODE_TERM).

### Requirement 5: KG Relevance Score Serialization

**User Story:** As a developer, I want hop-distance-based KG relevance scores to be correctly serialized and deserialized in the ChunkSourceMapping model, so that scoring information is preserved across the retrieval pipeline.

#### Acceptance Criteria

1. WHEN a ChunkSourceMapping is serialized to a dictionary, THE ChunkSourceMapping SHALL include the hop_distance and the computed relevance score in the output.
2. WHEN a ChunkSourceMapping is deserialized from a dictionary, THE ChunkSourceMapping SHALL reconstruct the hop_distance and recompute the relevance score using the same decay formula.
3. THE ChunkSourceMapping `get_relevance_score()` method SHALL use the configurable decay factor (default 0.5) consistent with the KGRetrievalService scoring.
