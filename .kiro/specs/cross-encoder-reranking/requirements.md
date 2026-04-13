# Requirements Document

## Introduction

Replace the bi-encoder cosine similarity score (the "semantic" component) in the SemanticReranker's scoring formula with a cross-encoder relevance score. The cross-encoder model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) will be hosted on the existing model-server Docker container and exposed via a new `/rerank` endpoint. The bi-encoder approach embeds query and document independently, missing token-level cross-attention — this causes proper nouns like "Chelsea" to rank below generic concept matches. The cross-encoder processes query-document pairs jointly through a transformer, enabling cross-attention that correctly recognizes entity matches.

## Glossary

- **Model_Server**: The dedicated ML inference Docker container (`Dockerfile.model-server`) running FastAPI on port 8001, currently serving embedding and NLP models
- **Cross_Encoder**: A transformer model (`cross-encoder/ms-marco-MiniLM-L-6-v2`, ~80MB) that scores query-document pairs jointly, producing a single relevance score per pair
- **Bi_Encoder**: The current approach using `BAAI/bge-base-en-v1.5` to embed query and document independently, then measuring cosine similarity
- **SemanticReranker**: The component in `semantic_reranker.py` that combines KG relevance scores with semantic scores to produce final chunk rankings
- **Model_Server_Client**: The async HTTP client (`model_server_client.py`) in the app container that communicates with the Model_Server
- **Rerank_Endpoint**: The new `/rerank` POST endpoint on the Model_Server that accepts query-document pairs and returns cross-encoder relevance scores
- **Scoring_Weights**: The configurable weights in `scoring_weights.py` controlling the KG vs semantic balance (default 0.7 / 0.3)
- **Query_Document_Pair**: A tuple of (query text, document text) submitted to the Cross_Encoder for joint scoring

## Requirements

### Requirement 1: Cross-Encoder Model Loading on Model Server

**User Story:** As a system operator, I want the cross-encoder model pre-loaded on the Model_Server at startup, so that reranking requests are served without cold-start latency.

#### Acceptance Criteria

1. WHEN the Model_Server starts with PRELOAD_MODELS=true, THE Model_Server SHALL load the `cross-encoder/ms-marco-MiniLM-L-6-v2` model into memory alongside the existing embedding and NLP models
2. THE Model_Server SHALL expose a `CROSS_ENCODER_MODEL` environment variable (default: `cross-encoder/ms-marco-MiniLM-L-6-v2`) to configure which cross-encoder model to load
3. WHEN the Cross_Encoder model fails to load, THE Model_Server SHALL log the error and continue serving embedding and NLP requests without the reranking capability
4. THE Dockerfile.model-server SHALL pre-download the Cross_Encoder model at build time to avoid runtime downloads
5. WHEN the `/health/ready` endpoint is called, THE Model_Server SHALL include the Cross_Encoder model's loaded status in the health response

### Requirement 2: Rerank API Endpoint on Model Server

**User Story:** As the app container, I want a `/rerank` endpoint on the Model_Server that accepts query-document pairs and returns relevance scores, so that the SemanticReranker can use cross-encoder scoring.

#### Acceptance Criteria

1. THE Rerank_Endpoint SHALL accept a POST request with a JSON body containing a `query` string and a `documents` list of strings
2. THE Rerank_Endpoint SHALL return a JSON response containing a `scores` list of floats, one per document, in the same order as the input documents
3. WHEN the `documents` list is empty, THE Rerank_Endpoint SHALL return an empty `scores` list
4. WHEN the Cross_Encoder model is not loaded, THE Rerank_Endpoint SHALL return HTTP 503 with a descriptive error message
5. THE Rerank_Endpoint SHALL normalize the raw Cross_Encoder logits to the range [0, 1] using a sigmoid function before returning scores
6. WHEN the `query` string is empty or missing, THE Rerank_Endpoint SHALL return HTTP 422 with a validation error

### Requirement 3: Model Server Client Rerank Method

**User Story:** As the SemanticReranker, I want the Model_Server_Client to provide a `rerank` method, so that I can obtain cross-encoder scores for query-document pairs.

#### Acceptance Criteria

1. THE Model_Server_Client SHALL provide an async `rerank` method that accepts a query string and a list of document strings and returns a list of float scores
2. WHEN the Model_Server is unavailable or the Rerank_Endpoint returns an error, THE Model_Server_Client `rerank` method SHALL raise a `ModelServerError` or `ModelServerUnavailable` exception
3. THE Model_Server_Client `rerank` method SHALL use the same retry logic and connection pooling as the existing `generate_embeddings` method

### Requirement 4: SemanticReranker Cross-Encoder Integration

**User Story:** As a user searching for "Chelsea AI Ventures", I want the SemanticReranker to use cross-encoder scoring instead of bi-encoder cosine similarity, so that proper noun matches rank correctly above generic concept matches.

#### Acceptance Criteria

1. WHEN the Model_Server_Client is available and the Rerank_Endpoint is healthy, THE SemanticReranker SHALL use cross-encoder scores from the Rerank_Endpoint as the semantic component in the scoring formula
2. THE SemanticReranker SHALL pass the original query and chunk content texts to the Model_Server_Client `rerank` method in a single batch call per reranking invocation
3. THE SemanticReranker SHALL use the cross-encoder scores directly as `semantic_score` on each chunk (scores are already normalized to [0, 1] by the Rerank_Endpoint)
4. THE SemanticReranker SHALL preserve the existing final score formula: `final_score = (kg_relevance_score × KG_WEIGHT) + (semantic_score × SEMANTIC_WEIGHT) + entity/action boosts`
5. THE Scoring_Weights (KG_WEIGHT=0.7, SEMANTIC_WEIGHT=0.3) SHALL remain configurable via environment variables and `scoring_weights.py`

### Requirement 5: Graceful Fallback to Bi-Encoder

**User Story:** As a system operator, I want the SemanticReranker to fall back to bi-encoder cosine similarity when the cross-encoder endpoint is unavailable, so that search continues to function during model server issues.

#### Acceptance Criteria

1. IF the Model_Server_Client `rerank` call fails or times out, THEN THE SemanticReranker SHALL fall back to the existing bi-encoder cosine similarity scoring for that reranking invocation
2. WHEN a fallback occurs, THE SemanticReranker SHALL log a warning indicating the fallback reason
3. WHILE the Cross_Encoder is unavailable, THE SemanticReranker SHALL continue to use the same KG_WEIGHT and SEMANTIC_WEIGHT for the bi-encoder fallback scores
4. THE SemanticReranker SHALL attempt the cross-encoder path on each new reranking invocation (no persistent circuit-breaker disabling the cross-encoder)

### Requirement 6: Dockerfile and Infrastructure Updates

**User Story:** As a DevOps engineer, I want the Dockerfile.model-server and docker-compose.yml updated to support the cross-encoder model, so that the model is available in all environments.

#### Acceptance Criteria

1. THE Dockerfile.model-server SHALL include a build step that pre-downloads the `cross-encoder/ms-marco-MiniLM-L-6-v2` model weights
2. THE docker-compose.yml SHALL pass the `CROSS_ENCODER_MODEL` environment variable to the model-server service
3. THE Model_Server container SHALL remain within its existing 4GB memory limit after loading the Cross_Encoder model (~80MB) alongside the existing models
