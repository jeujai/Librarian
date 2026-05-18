## Purpose

This feature restructures the search pipeline in `RAGService._search_documents` to fix the inverted priority chain and integrates SearXNG as a supplementary web search source.

The current `_search_documents` method has a flawed priority chain: Source Prioritization Engine (semantic search + Librarian boost) runs first and short-circuits KG-guided retrieval entirely. Source Prioritization and the semantic search fallback are essentially the same thing (both do vector search) with different reranking. KG Retrieval, which uses graph traversal for precise chunk retrieval, is only reached when Source Prioritization is unavailable.

The desired architecture redefines the pipeline as two distinct phases:

1. **Retrieval phase**: KG Retrieval first, graceful degradation to semantic search.
2. **Post-processing phase**: Source Prioritization applied as a reranking/tagging layer on all results from the retrieval phase, plus optional SearXNG web results merged in when Librarian results are thin.

Source Prioritization stops being an alternative search strategy and becomes what it should be: a reranking/tagging layer that runs on the output of whatever search strategy produced the results.


### Key Terms
- **Search_Pipeline**: The `_search_documents` method in `RAGService` that orchestrates retrieval of document chunks for a given query.
- **Retrieval_Phase**: The first phase of the Search_Pipeline that finds relevant chunks using KG_Retrieval or Semantic_Search.
- **Post_Processing_Phase**: The second phase of the Search_Pipeline that tags, boosts, optionally supplements with web results, and ranks all chunks from the Retrieval_Phase.
- **KG_Retrieval**: Knowledge-graph-guided retrieval via `KGRetrievalService`, which uses Neo4j graph traversal (concept relationships, `source_chunks` pointers, multi-hop reasoning) to find relevant chunks.
- **Semantic_Search**: Plain vector similarity search via the vector store client (Milvus locally, OpenSearch in AWS).
- **Source_Prioritization_Layer**: A post-processing reranking/tagging layer that tags each result with its source type (`LIBRARIAN` or `WEB_SEARCH`) and applies a configurable boost factor to Librarian document scores.
- **SearXNG_Client**: An async HTTP client that calls the SearXNG JSON API to retrieve web search results.
- **SearXNG_Service**: The self-hosted SearXNG Docker container that provides meta-search capabilities.
- **Librarian_Result**: A search result originating from documents uploaded to the Multimodal Librarian system.
- **Web_Result**: A search result originating from SearXNG web search.
- **Confidence_Threshold**: A configurable minimum score below which results are discarded.
- **Result_Count_Threshold**: A configurable minimum number of Librarian results below which web search is triggered as supplementary.
- **DI_Provider**: A FastAPI dependency injection provider function in `services.py` that lazily initializes and caches a service instance.

## Requirements

### Requirement: Retrieval Phase — KG Retrieval as Primary Path

The system SHALL support: As a user querying the system, I want the search pipeline to use knowledge graph traversal first, so that I get the most contextually relevant results based on concept relationships rather than just vector similarity.

#### Scenario: WHEN a query is submitted to the Search_Pipeline and KG_Retr

- **THEN** WHEN a query is submitted to the Search_Pipeline and KG_Retrieval is available, THE Retrieval_Phase SHALL attempt KG_Retrieval first.

#### Scenario: WHEN KG_Retrieval returns chunks that pass filtering, THE Re

- **THEN** WHEN KG_Retrieval returns chunks that pass filtering, THE Retrieval_Phase SHALL use those chunks as the result set and skip Semantic_Search.

#### Scenario: WHEN KG_Retrieval is unavailable, returns no usable chunks,

- **THEN** WHEN KG_Retrieval is unavailable, returns no usable chunks, or raises an exception, THE Retrieval_Phase SHALL fall back to Semantic_Search.

#### Scenario: IF KG_Retrieval raises an exception, THEN THE Retrieval_Phas

- **GIVEN** KG_Retrieval raises an exception
- **THEN** IF KG_Retrieval raises an exception, THEN THE Retrieval_Phase SHALL log the error and proceed to Semantic_Search without propagating the exception.

#### Scenario: THE Retrieval_Phase SHALL pass its result set to the Post_Pr

- **THEN** THE Retrieval_Phase SHALL pass its result set to the Post_Processing_Phase regardless of which retrieval strategy produced the chunks.

### Requirement: Post-Processing Phase — Source Prioritization as Reranking/Tagging Layer

The system SHALL support: As a user, I want all search results tagged with their source type and Librarian documents boosted, so that my uploaded documents are prioritized in responses regardless of how they were retrieved.

#### Scenario: THE Post_Processing_Phase SHALL run on every result set prod

- **THEN** THE Post_Processing_Phase SHALL run on every result set produced by the Retrieval_Phase, whether chunks came from KG_Retrieval or Semantic_Search.

#### Scenario: WHEN the Source_Prioritization_Layer processes results, THE

- **THEN** WHEN the Source_Prioritization_Layer processes results, THE Source_Prioritization_Layer SHALL tag each chunk with a `source_type` of `LIBRARIAN`.

#### Scenario: WHEN the Source_Prioritization_Layer processes Librarian res

- **THEN** WHEN the Source_Prioritization_Layer processes Librarian results, THE Source_Prioritization_Layer SHALL multiply each Librarian result score by the configurable `librarian_boost_factor`, capping the boosted score at 1.

#### Scenario: 

- **THEN** 

#### Scenario: WHEN the Source_Prioritization_Layer merges Librarian and We

- **THEN** WHEN the Source_Prioritization_Layer merges Librarian and Web results, THE Source_Prioritization_Layer SHALL sort all results by boosted score in descending order.

#### Scenario: WHEN two results have equal boosted scores, THE Source_Prior

- **THEN** WHEN two results have equal boosted scores, THE Source_Prioritization_Layer SHALL rank the Librarian_Result above the Web_Result.

### Requirement: Supplementary Web Search via SearXNG

The system SHALL support: As a user, I want the system to supplement my queries with web search results when my uploaded documents don't have enough relevant content, so that I still get useful answers.

#### Scenario: WHEN the number of Librarian results from the Retrieval_Phas

- **THEN** WHEN the number of Librarian results from the Retrieval_Phase is below the configurable Result_Count_Threshold, THE Post_Processing_Phase SHALL invoke the SearXNG_Client to fetch supplementary Web_Results.

#### Scenario: WHEN `searxng_enabled` is `false` or the SearXNG_Client is u

- **THEN** WHEN `searxng_enabled` is `false` or the SearXNG_Client is unavailable, THE Post_Processing_Phase SHALL skip web search regardless of Librarian result count.

#### Scenario: WHEN the SearXNG_Client receives a query, THE SearXNG_Client

- **THEN** WHEN the SearXNG_Client receives a query, THE SearXNG_Client SHALL send an HTTP GET request to the SearXNG JSON API endpoint and return parsed results.

#### Scenario: WHEN the SearXNG_Client receives a successful response, THE

- **THEN** WHEN the SearXNG_Client receives a successful response, THE SearXNG_Client SHALL convert each result into a search result with `source_type` set to `WEB_SEARCH`.

#### Scenario: IF the SearXNG_Client request fails or times out, THEN THE P

- **GIVEN** the SearXNG_Client request fails or times out
- **THEN** IF the SearXNG_Client request fails or times out, THEN THE Post_Processing_Phase SHALL proceed with only Librarian results and log the failure.

#### Scenario: WHEN Web_Results are merged with Librarian results, THE Sour

- **THEN** WHEN Web_Results are merged with Librarian results, THE Source_Prioritization_Layer SHALL ensure Librarian results outrank equivalently-scored Web_Results due to the boost factor.

### Requirement: SearXNG Docker Service

The system SHALL support: As a developer, I want SearXNG running as a Docker Compose service, so that web search is available in the local development environment without external dependencies.

#### Scenario: THE SearXNG_Service SHALL be defined as a service in `docker

- **THEN** THE SearXNG_Service SHALL be defined as a service in `docker-compose.yml` using the `searxng/searxng` Docker image.

#### Scenario: THE SearXNG_Service SHALL expose a port for the JSON API acc

- **THEN** THE SearXNG_Service SHALL expose a port for the JSON API accessible from the app container via the Docker network.

#### Scenario: THE SearXNG_Service SHALL be configured to return JSON forma

- **THEN** THE SearXNG_Service SHALL be configured to return JSON format responses.

#### Scenario: THE SearXNG_Service SHALL be optional — the app container SH

- **THEN** THE SearXNG_Service SHALL be optional — the app container SHALL start and operate without the SearXNG_Service running.

#### Scenario: THE SearXNG_Service SHALL be connected to the existing `app-

- **THEN** THE SearXNG_Service SHALL be connected to the existing `app-network` Docker network.

### Requirement: SearXNG Client with Dependency Injection

The system SHALL support: As a developer, I want the SearXNG client to follow the existing DI patterns, so that it integrates cleanly with the codebase and is testable.

#### Scenario: THE SearXNG_Client SHALL be implemented as an async class in

- **THEN** THE SearXNG_Client SHALL be implemented as an async class in `src/multimodal_librarian/clients/searxng_client.py`.

#### Scenario: THE SearXNG_Client SHALL use `aiohttp` for HTTP requests.

- **THEN** THE SearXNG_Client SHALL use `aiohttp` for HTTP requests.

#### Scenario: THE SearXNG_Client SHALL read its configuration (host, port,

- **THEN** THE SearXNG_Client SHALL read its configuration (host, port, timeout, enabled flag) from the `Settings` class in `config.py`.

#### Scenario: A DI_Provider `get_searxng_client` SHALL be created in `serv

- **THEN** A DI_Provider `get_searxng_client` SHALL be created in `services.py` following the lazy initialization and singleton caching pattern.

#### Scenario: A DI_Provider `get_searxng_client_optional` SHALL be created

- **THEN** A DI_Provider `get_searxng_client_optional` SHALL be created that returns `None` when SearXNG is disabled or unavailable.

#### Scenario: WHEN the SearXNG_Client is instantiated, THE SearXNG_Client

- **THEN** WHEN the SearXNG_Client is instantiated, THE SearXNG_Client SHALL NOT establish any connections until a search method is called.

### Requirement: Configuration Settings

The system SHALL support: As a developer, I want all new search pipeline and SearXNG settings to be configurable via environment variables, so that behavior can be tuned without code changes.

#### Scenario: THE Settings class SHALL include fields for `searxng_host`,

- **THEN** THE Settings class SHALL include fields for `searxng_host`, `searxng_port`, `searxng_timeout`, and `searxng_enabled` with sensible defaults.

#### Scenario: THE Settings class SHALL include a field for `web_search_res

- **THEN** THE Settings class SHALL include a field for `web_search_result_count_threshold` that controls when web search is triggered.

#### Scenario: THE Settings class SHALL include a field for `searxng_max_re

- **THEN** THE Settings class SHALL include a field for `searxng_max_results` that controls the maximum number of web results to fetch.

#### Scenario: THE `.env.local` file SHALL include default values for all S

- **THEN** THE `.env.local` file SHALL include default values for all SearXNG-related environment variables.

#### Scenario: WHEN `searxng_enabled` is set to `false`, THE Search_Pipelin

- **THEN** WHEN `searxng_enabled` is set to `false`, THE Search_Pipeline SHALL skip web search entirely regardless of Librarian result count.

### Requirement: Graceful Degradation

The system SHALL support: As a user, I want the search system to always return the best available results even when some components are down, so that I never get an empty response when data exists.

#### Scenario: WHEN KG_Retrieval is unavailable and Semantic_Search is avai

- **THEN** WHEN KG_Retrieval is unavailable and Semantic_Search is available, THE Search_Pipeline SHALL return Semantic_Search results with the Post_Processing_Phase applied.

#### Scenario: WHEN both KG_Retrieval and SearXNG_Client are unavailable, T

- **THEN** WHEN both KG_Retrieval and SearXNG_Client are unavailable, THE Search_Pipeline SHALL return Semantic_Search results with the Post_Processing_Phase applied.

#### Scenario: WHEN Semantic_Search is unavailable and KG_Retrieval is unav

- **THEN** WHEN Semantic_Search is unavailable and KG_Retrieval is unavailable, THE Search_Pipeline SHALL return an empty result set without raising an exception.

#### Scenario: IF any individual stage raises an exception, THEN THE Search

- **GIVEN** any individual stage raises an exception
- **THEN** IF any individual stage raises an exception, THEN THE Search_Pipeline SHALL log the error and continue to the next stage.
