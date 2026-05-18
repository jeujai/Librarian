## Purpose

The Chelsea query ("What did our team observe at Chelsea?") returns irrelevant results from computer vision textbooks, probability theory, and game theory instead of the expected GenLang book page 114 content about Chelsea AI Ventures. The root cause is a two-part interaction: (1) `QueryDecomposer._find_semantic_matches()` returns 20 concept matches including many noisy generic phrases like "we observe" and "we saw" alongside the actual "Chelsea" concept, and (2) `_aggregate_and_deduplicate()` applies a `coverage_bonus = log2(num_concepts) * 0.1` that rewards chunks matching many concepts — so chunks matching 8 generic observation-related concepts get a +0.3 bonus while the Chelsea-specific chunk matching only 1 concept gets +0.0, pushing irrelevant results above the correct ones.


### Defect Description
1.1 WHEN a query like "What did our team observe at Chelsea?" is decomposed by `_find_semantic_matches()` THEN the system returns 20 semantic concept matches including generic phrases ("we observe" sim=0.8369, "we saw" sim=0.8288, "scrutinized" sim=0.8246) alongside the relevant "Chelsea" concept (sim=0.8454)

1.2 WHEN `_aggregate_and_deduplicate()` scores chunks that match many generic semantic concepts (e.g., 8 observation-related concepts) THEN the system assigns a coverage_bonus of `log2(8) * 0.1 = 0.3`, inflating the kg_relevance_score of irrelevant chunks above Chelsea-specific chunks that match only 1 concept (coverage_bonus = `log2(1) * 0.1 = 0.0`)

1.3 WHEN the inflated irrelevant chunks rank higher than Chelsea-specific chunks THEN the system returns unrelated content from computer vision textbooks, probability theory, and game theory as top results, or falls through to SearXNG web search returning Chelsea FC football results

1.4 WHEN `_find_semantic_matches()` uses `semantic_max_results=20` and `similarity_threshold=0.75` THEN the system retrieves an excessive number of low-quality concept matches for queries containing common observation verbs, inflating `stage1_chunk_count` to 89 via EXTRACTED_FROM edges

## Requirements

### Requirement: Expected Behavior: Bugfix

The system SHALL correctly handle bugfix as specified in the expected behavior.

#### Scenario 2.1

- **WHEN** a query like "What did our team observe at Chelsea?" is decomposed by `_find_semantic_matches()`
- **THEN** the system SHALL return a focused set of concept matches (approximately 1-5) that are semantically relevant to the query's core intent, filtering out generic verb-derived concepts like "we observe" and "we saw"

#### Scenario 2.2

- **WHEN** `_aggregate_and_deduplicate()` scores chunks
- **THEN** the system SHALL not allow coverage_bonus from generic/low-specificity concepts to outweigh a chunk's direct relevance to the query's named entities, ensuring that a chunk matching the specific "Chelsea" concept ranks above chunks that only match generic observation concepts

#### Scenario 2.3

- **WHEN** the Chelsea query is processed end-to-end
- **THEN** the system SHALL return chunks from the GenLang book discussing Chelsea AI Ventures observations, with GenLang book page 114 as the top source

#### Scenario 2.4

- **WHEN** `_find_semantic_matches()` returns concept matches
- **THEN** the system SHALL limit or filter results so that generic verb-derived concepts do not dominate the match set, keeping the concept count proportional to the query's actual semantic complexity

### Requirement: Regression Prevention: Bugfix

The system SHALL CONTINUE TO maintain existing correct behavior for bugfix after the fix.

#### Scenario 3.1

- **WHEN** a query contains only specific named entities (e.g., "Tell me about Neo4j") with no generic verb phrases
- **THEN** the system SHALL CONTINUE TO return relevant concept matches and correctly ranked chunks for those entities

#### Scenario 3.2

- **WHEN** a query matches multiple genuinely distinct concepts (e.g., "Compare Chelsea and Venezuela observations")
- **THEN** the system SHALL CONTINUE TO apply coverage_bonus to reward chunks that sit at the intersection of multiple relevant concepts

#### Scenario 3.3

- **WHEN** semantic matching is unavailable (no model server)
- **THEN** the system SHALL CONTINUE TO fall back to lexical matching as the existing fallback strategy

#### Scenario 3.4

- **WHEN** a query has no matching concepts in the knowledge graph
- **THEN** the system SHALL CONTINUE TO set `has_kg_matches=False` and signal fallback mode

#### Scenario 3.5

- **WHEN** `_aggregate_and_deduplicate()` processes related chunks from relationship traversal
- **THEN** the system SHALL CONTINUE TO apply hop-distance decay scoring and cap related chunks at `_max_related_chunks`
