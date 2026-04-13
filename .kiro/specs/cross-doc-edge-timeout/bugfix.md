# Bugfix Requirements Document

## Introduction

The `_discover_cross_doc_edges()` method in `CompositeScoreEngine` times out on every batch during document enrichment. The batch Cypher query performs an unbounded traversal across all concepts of the source document (~7,700+), through all qualifying relationship types, to all concepts of each target document, while also computing `gds.similarity.cosine()` on embedding vectors for every matched pair. With a batch size of 3 target documents and thousands of concepts per document, the combinatorial explosion exceeds the 120-second Neo4j transaction timeout. This results in ~26 minutes of wasted time per document enrichment with zero cross-document edges ever being discovered or created.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `_discover_cross_doc_edges()` executes its batch Cypher query against a source document with thousands of concepts (e.g., ~7,700) and a batch of 3 target documents that also have thousands of concepts each THEN the system times out with a `TransactionTimedOutClientConfiguration` error after 120 seconds and returns zero results for that batch

1.2 WHEN the batch query performs the pattern match `(ch1:Chunk)<-[:EXTRACTED_FROM]-(c1:Concept)-[r]-(c2:Concept)-[:EXTRACTED_FROM]->(ch2:Chunk)` across all concepts of the source document and all concepts of the target documents THEN the system creates a combinatorial explosion of traversals that cannot complete within the transaction timeout

1.3 WHEN every batch in the cross-doc edge discovery times out (approximately 13 batches per document at batch size 3 with ~37 target documents) THEN the system wastes approximately 26 minutes per document enrichment with zero RELATED_DOCS edges ever being created

1.4 WHEN the batch query computes `gds.similarity.cosine()` on embedding vectors for every concept pair matched in the traversal THEN the system adds significant per-row computation cost on top of the already expensive traversal, further contributing to the timeout

### Expected Behavior (Correct)

2.1 WHEN `_discover_cross_doc_edges()` executes against a source document with thousands of concepts and target documents that also have thousands of concepts THEN the system SHALL complete each batch query within the Neo4j transaction timeout (120 seconds) and return discovered cross-document edges

2.2 WHEN the cross-doc edge discovery query runs THEN the system SHALL use a query strategy that avoids the combinatorial explosion of traversing all source concepts × all relationship types × all target concepts in a single pattern match

2.3 WHEN cross-doc edge discovery completes for a document THEN the system SHALL have discovered and returned actual cross-document concept pairs where they exist, enabling RELATED_DOCS edges to be created

2.4 WHEN computing similarity between cross-document concept pairs THEN the system SHALL either defer cosine similarity computation to a later phase, compute it only for pre-filtered candidate pairs, or use an approach that does not add unbounded computation cost to the discovery traversal

### Unchanged Behavior (Regression Prevention)

3.1 WHEN cross-doc edge discovery runs for documents with small concept counts (e.g., fewer than 100 concepts) THEN the system SHALL CONTINUE TO discover cross-document edges correctly as it would have if the query had not timed out

3.2 WHEN edge scores are computed from discovered cross-document edges THEN the system SHALL CONTINUE TO use the three-signal formula (type_weight × 0.4 + embedding_similarity × 0.45 + cn_weight × 0.15) clamped to [0.0, 1.0]

3.3 WHEN document-pair scores are aggregated from edge scores THEN the system SHALL CONTINUE TO apply the MIN_EDGE_SCORE, MIN_EMBEDDING_SIMILARITY, and MIN_EDGES_FOR_PAIR filters before aggregation

3.4 WHEN RELATED_DOCS edges are persisted THEN the system SHALL CONTINUE TO upsert them bidirectionally with representative concepts and the same score/metadata properties

3.5 WHEN conversation documents are encountered THEN the system SHALL CONTINUE TO skip them in both source and target roles during cross-doc edge discovery

3.6 WHEN the qualifying relationship types are evaluated THEN the system SHALL CONTINUE TO use the same set of 13 relationship types (SAME_AS, IsA, PartOf, RelatedTo, UsedFor, CapableOf, HasProperty, AtLocation, Causes, HasPrerequisite, MotivatedByGoal, Synonym, SimilarTo)

3.7 WHEN per-target-doc edge capping is applied THEN the system SHALL CONTINUE TO limit results to MAX_EDGES_PER_TARGET_DOC (200) edges per target document
