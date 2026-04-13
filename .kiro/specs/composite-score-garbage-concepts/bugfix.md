# Bugfix Requirements Document

## Introduction

The `CompositeScoreEngine._discover_cross_doc_edges` method produces false positive cross-document relationships by matching on garbage concepts that share identical `name_lower` values across documents. These garbage concepts originate from PDF extraction artifacts, hyphenation breaks, generic phrases, table references, time expressions, stage/phase labels, and citations. Because the discovery query only requires multi-token names (`name CONTAINS ' '`) without filtering on `concept_type` or textual patterns, garbage concepts with `NULL` concept_type pass through and receive 1.0 cosine similarity (identical strings), inflating document-pair scores. This causes unrelated documents (e.g., a medical standards-of-care document and a Machine Learning Systems document) to appear as highly related (85%) linked by concepts like "? Weight".

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a concept name contains PDF artifact characters (e.g., "? Weight", "+ +", "n +", "p =") THEN the system includes it in cross-document edge discovery and scores it as a valid shared concept

1.2 WHEN a concept name contains hyphenation break patterns (e.g., "sec- tion", "includ- ing") THEN the system includes it in cross-document edge discovery and scores it as a valid shared concept

1.3 WHEN a concept name is a generic non-domain phrase (e.g., "less than", "more than two", "information about") THEN the system includes it in cross-document edge discovery and scores it as a valid shared concept

1.4 WHEN a concept name is a table reference, time expression, stage/phase label, or citation (e.g., "Table 15.2", "10 years", "30 days", "stage 2", "phase 3", "et al.") THEN the system includes it in cross-document edge discovery and scores it as a valid shared concept

1.5 WHEN both concepts in a matched pair have NULL concept_type THEN the system treats the pair as a valid cross-document edge without requiring any domain-specific type classification

1.6 WHEN multiple garbage concepts match across two unrelated documents THEN the system aggregates their edge scores into a high document-pair score, creating a false RELATED_DOCS edge (e.g., 85% relatedness between a medical and an ML document)

### Expected Behavior (Correct)

2.1 WHEN a concept name contains PDF artifact patterns (characters like ?, +, = adjacent to word boundaries, or patterns like "n +", "p =") THEN the system SHALL exclude it from cross-document edge discovery

2.2 WHEN a concept name contains hyphenation break patterns (a word fragment followed by "- " and another word fragment) THEN the system SHALL exclude it from cross-document edge discovery

2.3 WHEN a concept name matches a known generic non-domain phrase pattern (e.g., "less than", "more than", "information about", and similar filler phrases) THEN the system SHALL exclude it from cross-document edge discovery

2.4 WHEN a concept name matches a table reference, time expression, stage/phase label, or citation pattern (e.g., "Table N.N", "N years/days/months", "stage/phase N", "et al.") THEN the system SHALL exclude it from cross-document edge discovery

2.5 WHEN both concepts in a matched pair have NULL concept_type THEN the system SHALL exclude the pair from cross-document edge discovery, requiring at least one concept to have a non-null concept_type from DOMAIN_CONCEPT_TYPES

2.6 WHEN garbage concepts are filtered out THEN the system SHALL produce document-pair scores that reflect only genuine domain-specific concept overlap, preventing false RELATED_DOCS edges between unrelated documents

### Unchanged Behavior (Regression Prevention)

3.1 WHEN concepts have valid multi-token domain names (e.g., "machine learning", "neural network", "clinical trial") and at least one has a non-null concept_type THEN the system SHALL CONTINUE TO discover and score them as cross-document edges

3.2 WHEN concepts have UMLS semantic types (e.g., "Disease or Syndrome", "Organic Chemical") THEN the system SHALL CONTINUE TO include them in cross-document edge discovery regardless of token count

3.3 WHEN concepts have trusted NER types (e.g., ORG, PERSON) THEN the system SHALL CONTINUE TO include them in cross-document edge discovery

3.4 WHEN the per-edge scoring formula (type_weight × 0.4 + embedding_similarity × 0.45 + cn_weight × 0.15) is applied to qualifying edges THEN the system SHALL CONTINUE TO compute scores identically

3.5 WHEN document-pair aggregation applies MIN_EDGE_SCORE, MIN_EMBEDDING_SIMILARITY, and MIN_EDGES_FOR_PAIR thresholds THEN the system SHALL CONTINUE TO filter and aggregate identically

3.6 WHEN conversation documents are encountered THEN the system SHALL CONTINUE TO exclude them from cross-document edge discovery
