# Model Server Separation Tasks

## Task 1: Create Model Server Service
Create the dedicated model server FastAPI application.

- [x] 1.1 Create `src/model_server/` directory structure
- [x] 1.2 Implement `src/model_server/config.py` with configuration settings
- [x] 1.3 Implement `src/model_server/models/embedding.py` - embedding model wrapper
  - Load sentence-transformers model on startup
  - Provide `encode()` method for batch embedding generation
  - Track model loading status and timing
- [x] 1.4 Implement `src/model_server/models/nlp.py` - NLP model wrapper
  - Load spacy model on startup
  - Provide methods for tokenization, NER, POS tagging
  - Track model loading status and timing
- [x] 1.5 Implement `src/model_server/api/embeddings.py` - embedding endpoints
  - POST /embeddings endpoint with batch support
  - Input validation with Pydantic models
  - Error handling for model not ready
- [x] 1.6 Implement `src/model_server/api/nlp.py` - NLP endpoints
  - POST /nlp/process endpoint with task selection
  - Support for tokenize, ner, pos tasks
  - Batch processing support
- [x] 1.7 Implement `src/model_server/api/health.py` - health endpoints
  - GET /health with model status details
  - GET /health/ready for readiness probe
  - GET /health/live for liveness probe
- [x] 1.8 Implement `src/model_server/main.py` - FastAPI application
  - Lifespan context manager for model loading
  - CORS configuration
  - Request logging middleware

## Task 2: Create Model Server Docker Configuration
Set up Docker build and compose configuration for model server.

- [x] 2.1 Create `requirements-model-server.txt` with minimal dependencies
  - fastapi, uvicorn
  - sentence-transformers
  - spacy
  - pydantic
- [x] 2.2 Create `Dockerfile.model-server`
  - Base Python 3.11-slim image
  - Pre-download models at build time for faster startup
  - Proper layer caching for dependencies
- [x] 2.3 Update `docker-compose.yml` with model-server service
  - Service definition with health check
  - Volume for model cache persistence
  - Resource limits (memory)
  - Network configuration
- [x] 2.4 Update `docker-compose.yml` app service
  - Add depends_on for model-server
  - Add MODEL_SERVER_URL environment variable

## Task 3: Create Model Server Client
Implement the client library for the app to communicate with model server.

- [x] 3.1 Create `src/multimodal_librarian/clients/model_server_client.py`
  - Async HTTP client using aiohttp
  - Connection pooling
  - Retry logic with exponential backoff
  - Timeout handling
- [x] 3.2 Implement `generate_embeddings()` method
  - Batch support
  - Model selection parameter
  - Error handling and fallback
- [x] 3.3 Implement `process_nlp()` method
  - Task selection (tokenize, ner, pos)
  - Batch support
  - Error handling
- [x] 3.4 Implement `health_check()` and `wait_for_ready()` methods
  - Health status retrieval
  - Blocking wait with timeout for startup
- [x] 3.5 Add dependency injection provider in `api/dependencies/services.py`
  - `get_model_server_client()` function
  - Singleton pattern with lazy initialization
  - Cleanup on shutdown

## Task 4: Refactor Embedding Generation
Update existing code to use model server client instead of direct model loading.

- [x] 4.1 Update `src/multimodal_librarian/services/ai_service.py`
  - Add model server client as fallback/primary for embeddings
  - Keep external API providers (OpenAI, etc.) as alternatives
- [x] 4.2 Update `src/multimodal_librarian/components/vector_store/vector_store_optimized.py`
  - Replace direct SentenceTransformer usage with model client
  - Update `generate_embeddings_batch()` method
- [x] 4.3 Update `src/multimodal_librarian/components/vector_store/vector_operations_optimizer.py`
  - Replace EmbeddingGenerator class to use model client
  - Maintain batch processing interface
- [x] 4.4 Update `src/multimodal_librarian/services/async_embedding_service.py`
  - Use model server client for async embedding generation
  - Remove direct model loading

## Task 5: Refactor NLP Processing
Update existing code to use model server for NLP tasks.

- [x] 5.1 Update `src/multimodal_librarian/models/model_manager.py`
  - Remove direct spacy loading for document processing
  - Use model server client for NLP tasks
- [x] 5.2 Update any document processing code that uses spacy directly
  - Files to update: content_analyzer.py, gap_analyzer.py, query_understanding.py
  - Replace with model server client calls
  - Note: This is optional - local spacy can remain as fallback

## Task 6: Implement Graceful Degradation
Ensure app functions when model server is unavailable.

- [x] 6.1 Add fallback behavior in model server client
  - Return appropriate errors when server unavailable
  - Log connectivity issues clearly
- [x] 6.2 Update health check endpoints
  - Include model server status in health response
  - Report degraded status when model server unavailable
- [x] 6.3 Add configuration flag to disable model server
  - `MODEL_SERVER_ENABLED` environment variable
  - Fall back to direct model loading when disabled

## Task 7: Testing
Add tests for model server and client.

- [x] 7.1 Create unit tests for model server endpoints
  - Test embedding generation
  - Test NLP processing
  - Test health endpoints
- [x] 7.2 Create unit tests for model server client
  - Test retry logic
  - Test timeout handling
  - Test error handling
- [x] 7.3 Create integration tests
  - Test app with model server running
  - Test app behavior when model server unavailable
- [x] 7.4 Update existing tests that mock model loading
  - Mock model server client instead of direct models

## Task 8: Documentation
Update documentation for the new architecture.

- [x] 8.1 Update README.md with model server information
- [x] 8.2 Update DOCKER.md with new service configuration
- [x] 8.3 Add troubleshooting guide for model server issues

## Task 9: Remove Local Model Fallbacks from App Container
Remove all direct model loading code from the app container to ensure models are only sourced from the model server. This reduces app container size and startup time.

- [x] 9.1 Remove SentenceTransformer fallback from `async_embedding_service.py`
- [x] 9.2 Remove SentenceTransformer fallback from `vector_operations_optimizer.py`
- [x] 9.3 Remove SentenceTransformer fallback from `kg_query_engine.py` and `kg_builder.py`
- [x] 9.4 Remove SentenceTransformer fallback from `content_analyzer.py` and `gap_analyzer.py`
- [x] 9.5 Remove spacy loading from `content_analyzer.py`, `gap_analyzer.py`, `query_understanding.py`
- [x] 9.6 Remove spacy loading from `model_manager.py`, `loader_optimized.py`, `real_model_loader.py`
- [x] 9.7 Remove model loading from `cold_start_optimizer.py`
- [x] 9.8 Remove CrossEncoder fallback from `hybrid_search.py`
- [x] 9.9 Create `requirements-app.txt` with lightweight dependencies (no ML models)
- [x] 9.10 Create `Dockerfile.app` for lightweight app container
- [x] 9.11 Update `docker-compose.yml` to use lightweight app container
