# Requirements Document

## Introduction

The RAG retrieval pipeline currently reports high confidence scores (e.g. "100% relevant") even for completely off-topic queries because the scoring model (70% KG relevance + 30% semantic similarity) measures how well retrieved chunks match discovered concepts rather than whether those chunks actually answer the user's question. Generic words in any query match generic concepts in Neo4j, which link to chunks, producing falsely confident results.

This feature introduces two complementary detection mechanisms to identify "no relevant results" scenarios:

1. **Relative Semantic Floor Detection** — Analyze the score distribution of returned results. When top-N results cluster within a narrow band (low variance), nothing stands out, signaling irrelevance. Relevant queries produce score separation between best and worst results.

2. **Low KG Concept Specificity Detection** — Evaluate whether matched concepts are generic words ("world", "today", "going") versus domain-specific or proper-noun terms ("Chelsea", "RAG", "LangChain"). If only generic/low-specificity concepts matched, the query is likely off-topic for the corpus.

When both signals agree the results are irrelevant, the system triggers a supplementary web search (even when existing count/score thresholds would not have fired), adjusts the confidence score downward, and communicates uncertainty to the user instead of displaying misleading high-relevance percentages.

Additionally, the Relevance_Detector provides a **proper-noun-based chunk filtering** capability that operates as a pre-reranking filter. When a user query contains proper nouns (e.g. "Venezuela"), the KG may match concepts derived from conversations (e.g. `gpe_venezuela`) that link to hundreds of chunk IDs. After chunk resolution and deduplication, the candidate set (e.g. 57 chunks) is dominated by book chunks about generic related concepts (e.g. "president") that do not contain the proper noun. The Semantic_Reranker's top_k cutoff (e.g. 15) then eliminates the few chunks that actually contain the proper noun, because those chunks score lower on semantic similarity to the broader query. The proper-noun chunk filter runs before the reranker's top_k cutoff, keeping only chunks whose content contains at least one of the query's proper nouns. This ensures that conversation chunks (or any chunks) that genuinely contain the queried proper noun survive reranking and appear in the final citation list alongside supplementary web search results.

## Glossary

- **Relevance_Detector**: The component that evaluates retrieval result quality using score distribution analysis and concept specificity signals to determine whether results are genuinely relevant to the user's query.
- **Score_Distribution_Analyzer**: The sub-component of Relevance_Detector that computes statistical properties (variance, spread, clustering) of the final_score values across returned chunks.
- **Concept_Specificity_Analyzer**: The sub-component of Relevance_Detector that classifies matched KG concepts as generic or domain-specific based on lexical and structural heuristics.
- **Semantic_Floor**: The condition where all returned chunks have similar final_score values with low variance, indicating no result stands out as particularly relevant.
- **Concept_Specificity_Score**: A numeric score (0.0 to 1.0) assigned to each matched concept indicating how domain-specific the concept is, where 0.0 is fully generic and 1.0 is highly specific.
- **Relevance_Verdict**: The output of the Relevance_Detector containing a boolean is_relevant flag, a combined confidence adjustment factor, and diagnostic metadata explaining the detection reasoning.
- **RAG_Service**: The main retrieval-augmented generation service that orchestrates query processing, document search, and AI response generation.
- **Semantic_Reranker**: The component that re-ranks candidate chunks using a weighted combination of KG relevance scores (70%) and semantic similarity scores (30%).
- **Query_Decomposer**: The component that extracts concepts from user queries and matches them against the Neo4j knowledge graph.
- **Final_Score**: The weighted combination of kg_relevance_score (70%) and semantic_score (30%) assigned to each RetrievedChunk by the Semantic_Reranker.
- **Proper_Noun_Chunk_Filter**: A pre-reranking filter operation exposed by the Relevance_Detector that takes the full set of resolved candidate chunks and returns only those whose content contains at least one of the query's proper nouns.
- **KG_Retrieval_Service**: The service that orchestrates the two-stage KG retrieval pipeline: Stage 1 (concept-based candidate retrieval from Neo4j and chunk resolution from Milvus) and Stage 2 (semantic reranking with top_k cutoff).
- **Candidate_Chunks**: The full set of resolved and deduplicated chunks produced by Stage 1 of the KG retrieval pipeline, before the Semantic_Reranker applies its top_k cutoff.

## Requirements

### Requirement 1: Score Distribution Analysis

**User Story:** As a user, I want the system to detect when all retrieved results have uniformly mediocre scores, so that I am not shown misleadingly high confidence for off-topic queries.

#### Acceptance Criteria

1. WHEN the Semantic_Reranker produces a ranked list of chunks, THE Score_Distribution_Analyzer SHALL compute the variance and spread (max minus min) of the final_score values across the top-N results.
2. WHILE the spread of final_score values across the top-N results is below a configurable spread threshold, THE Score_Distribution_Analyzer SHALL classify the result set as exhibiting a Semantic_Floor pattern.
3. WHILE the variance of final_score values across the top-N results is below a configurable variance threshold, THE Score_Distribution_Analyzer SHALL classify the result set as exhibiting a Semantic_Floor pattern.
4. WHEN the result set contains fewer than 3 chunks, THE Score_Distribution_Analyzer SHALL skip distribution analysis and return an indeterminate result rather than classifying the set as relevant or irrelevant.
5. THE Score_Distribution_Analyzer SHALL return a dictionary containing the computed variance, spread, is_semantic_floor boolean, and the number of chunks analyzed.

### Requirement 2: Concept Specificity Analysis

**User Story:** As a user, I want the system to recognize when my query only matched generic dictionary words in the knowledge graph, so that the system does not treat those matches as evidence of relevance.

#### Acceptance Criteria

1. WHEN the Query_Decomposer returns concept_matches for a query, THE Concept_Specificity_Analyzer SHALL assign a Concept_Specificity_Score to each matched concept based on lexical heuristics including word length, capitalization, presence of underscores or hyphens, and whether the word appears in a generic-words list.
2. THE Concept_Specificity_Analyzer SHALL classify concepts that are single common English words shorter than 5 characters (e.g. "world", "today", "going") as low-specificity with a Concept_Specificity_Score below 0.3.
3. THE Concept_Specificity_Analyzer SHALL classify concepts that are proper nouns, multi-word phrases, or domain-specific terms (e.g. "Chelsea", "LangChain", "retrieval-augmented generation") as high-specificity with a Concept_Specificity_Score above 0.7.
4. WHEN all matched concepts have a Concept_Specificity_Score below a configurable specificity threshold, THE Concept_Specificity_Analyzer SHALL classify the query as having low concept specificity.
5. WHEN the Query_Decomposer returns zero concept_matches, THE Concept_Specificity_Analyzer SHALL classify the query as having low concept specificity.
6. THE Concept_Specificity_Analyzer SHALL return a dictionary containing the per-concept scores, the average specificity score, the is_low_specificity boolean, and the count of high-specificity versus low-specificity concepts.

### Requirement 3: Combined Relevance Detection

**User Story:** As a user, I want the system to combine score distribution and concept specificity signals into a single relevance verdict, so that the confidence score accurately reflects whether the retrieved results answer my question.

#### Acceptance Criteria

1. WHEN both the Score_Distribution_Analyzer detects a Semantic_Floor and the Concept_Specificity_Analyzer detects low concept specificity, THE Relevance_Detector SHALL produce a Relevance_Verdict with is_relevant set to false.
2. WHEN only one of the two signals (Semantic_Floor or low concept specificity) is detected, THE Relevance_Detector SHALL produce a Relevance_Verdict with is_relevant set to true but include a confidence penalty factor between 0.7 and 0.9.
3. WHEN neither signal is detected, THE Relevance_Detector SHALL produce a Relevance_Verdict with is_relevant set to true and a confidence adjustment factor of 1.0.
4. THE Relevance_Detector SHALL include diagnostic metadata in the Relevance_Verdict containing the score distribution analysis results, the concept specificity analysis results, and the reasoning for the verdict.
5. THE Relevance_Detector SHALL be callable as a standalone function that accepts a list of RetrievedChunk objects and a QueryDecomposition object and returns a Relevance_Verdict.

### Requirement 4: Integration with RAG Pipeline

**User Story:** As a developer, I want the relevance detection to integrate into the existing RAG pipeline without breaking current behavior, so that the feature can be enabled incrementally.

#### Acceptance Criteria

1. WHEN the RAG_Service executes the post-processing phase, THE RAG_Service SHALL invoke the Relevance_Detector before the web search decision and cache the Relevance_Verdict for downstream use.
2. WHEN the Relevance_Verdict indicates is_relevant is false, THE RAG_Service SHALL trigger a supplementary web search via SearXNG (if available and enabled), even when the existing count-based and score-based thresholds would not have triggered it.
3. WHEN the Relevance_Verdict indicates is_relevant is false and web search results are returned, THE RAG_Service SHALL drop the librarian chunks from the response, consistent with the existing behavior for irrelevant librarian results.
4. WHEN the RAG_Service computes the confidence score in _calculate_confidence_score, THE RAG_Service SHALL reuse the cached Relevance_Verdict and apply the confidence adjustment factor to the computed confidence score.
5. WHEN the Relevance_Verdict indicates is_relevant is false, THE RAG_Service SHALL set the confidence score to a value no higher than 0.3.
6. THE RAG_Service SHALL include the Relevance_Verdict diagnostic metadata in the RAGResponse metadata dictionary under the key "relevance_detection".
7. IF the Relevance_Detector raises an exception, THEN THE RAG_Service SHALL log the error, default to no web search trigger from relevance detection, and proceed with the original confidence score without applying any adjustment.
8. THE Relevance_Detector SHALL add no more than 5 milliseconds of latency to the RAG pipeline under normal operating conditions, as the analysis uses only in-memory statistical computations on already-retrieved data.

### Requirement 5: User-Facing Confidence Display

**User Story:** As a user, I want to see an honest confidence indicator when the system is unsure about the relevance of its results, so that I can judge whether to trust the response.

#### Acceptance Criteria

1. WHEN the Relevance_Verdict indicates is_relevant is false, THE Chat_Router SHALL display the relevance percentage with a qualifying label such as "low confidence" instead of showing a bare percentage.
2. WHEN the adjusted confidence score is below 0.3, THE Chat_Router SHALL append a disclaimer to the source citations indicating that the results may not be relevant to the query.
3. WHILE the Relevance_Verdict indicates is_relevant is true, THE Chat_Router SHALL display the relevance percentage using the existing format without modification.

### Requirement 6: Configuration and Thresholds

**User Story:** As a developer, I want the detection thresholds to be configurable, so that the feature can be tuned based on corpus characteristics and chunk sizes.

#### Acceptance Criteria

1. THE Relevance_Detector SHALL read the spread threshold, variance threshold, and specificity threshold from the application settings via Pydantic configuration.
2. THE Relevance_Detector SHALL use the following default threshold values: spread threshold of 0.05, variance threshold of 0.001, and specificity threshold of 0.3.
3. WHEN a threshold value is overridden via environment variable, THE Relevance_Detector SHALL use the overridden value instead of the default.
4. THE Relevance_Detector SHALL log the active threshold values at initialization for debugging purposes.

### Requirement 7: Proper-Noun-Based Pre-Reranking Chunk Filter

**User Story:** As a user, I want the system to preserve chunks that contain the proper nouns from my query before the reranker's top_k cutoff, so that conversation chunks (or any chunks) that previously answered the same question appear in the final citation list alongside web search results.

#### Acceptance Criteria

1. WHEN the query contains one or more proper nouns identified by spaCy NER, THE Relevance_Detector SHALL expose a filter_chunks_by_proper_nouns method that accepts the full set of Candidate_Chunks and the original query text and returns only those chunks whose content contains at least one of the query's proper nouns (case-insensitive substring match).
2. WHEN the Proper_Noun_Chunk_Filter produces a non-empty filtered set, THE KG_Retrieval_Service SHALL pass the filtered set to the Semantic_Reranker instead of the full Candidate_Chunks set, so that the reranker's top_k cutoff operates only on proper-noun-relevant chunks.
3. WHEN the Proper_Noun_Chunk_Filter produces an empty filtered set (no chunks contain any of the query's proper nouns), THE KG_Retrieval_Service SHALL fall back to passing the original unfiltered Candidate_Chunks to the Semantic_Reranker, preserving existing behavior.
4. WHEN the query contains no proper nouns (spaCy NER extracts zero named entities), THE KG_Retrieval_Service SHALL skip the Proper_Noun_Chunk_Filter and pass the full Candidate_Chunks to the Semantic_Reranker without modification.
5. THE Proper_Noun_Chunk_Filter SHALL operate on the Candidate_Chunks after the _aggregate_and_deduplicate step and before the Semantic_Reranker.rerank call within the KG_Retrieval_Service.retrieve method.
6. THE Proper_Noun_Chunk_Filter SHALL log the count of chunks before filtering, the count after filtering, the proper nouns used for filtering, and the chunk IDs that were retained.
7. THE Proper_Noun_Chunk_Filter SHALL reuse the spaCy NER model instance already loaded by the Relevance_Detector, adding no new model loading overhead.
8. IF the Proper_Noun_Chunk_Filter raises an exception, THEN THE KG_Retrieval_Service SHALL log the error and fall back to passing the original unfiltered Candidate_Chunks to the Semantic_Reranker.
9. THE Proper_Noun_Chunk_Filter SHALL add no more than 2 milliseconds of latency to the retrieval pipeline under normal operating conditions, as the filtering uses only in-memory string matching on already-resolved chunk content.
10. WHEN the Proper_Noun_Chunk_Filter retains chunks and the Relevance_Detector subsequently detects a proper-noun gap in the post-processing phase, THE RAG_Service selective drop logic SHALL find and retain the proper-noun-containing chunks that survived reranking, ensuring those chunks appear in the final response alongside any supplementary web search results.
