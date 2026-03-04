# Model Server Separation Requirements

## Overview
Separate ML model loading and inference into a dedicated container to improve development iteration speed and enable independent scaling of model inference.

## Problem Statement
Currently, ML models (sentence-transformers, spacy, etc.) are loaded directly in the main application container. This causes:
- **Slow development iteration**: Every app restart reloads all models (~30-60 seconds)
- **Resource coupling**: App and models compete for memory/CPU
- **No independent scaling**: Can't scale inference separately from API
- **Wasted resources**: Multiple app instances each load their own models

## User Stories

### 1. Fast Development Iteration
**As a** developer  
**I want** the application to start quickly after code changes  
**So that** I can iterate rapidly without waiting for model loading

#### Acceptance Criteria
- 1.1 Application container starts and responds to health checks within 5 seconds
- 1.2 Model server container loads models independently and persists across app restarts
- 1.3 Application can function in degraded mode if model server is unavailable
- 1.4 Hot reload of application code does not trigger model reloading

### 2. Model Inference API
**As a** developer  
**I want** a clean API for model inference  
**So that** I can easily generate embeddings and run NLP tasks

#### Acceptance Criteria
- 2.1 Model server exposes REST API for embedding generation
- 2.2 Model server exposes REST API for NLP tasks (tokenization, NER, etc.)
- 2.3 API supports batch processing for efficiency
- 2.4 API returns appropriate errors when models are not ready
- 2.5 API includes health check endpoint showing model loading status

### 3. Resource Isolation
**As an** operator  
**I want** models to run in a separate container  
**So that** I can allocate appropriate resources and scale independently

#### Acceptance Criteria
- 3.1 Model server container has dedicated memory allocation
- 3.2 Model server can be scaled independently of application
- 3.3 Multiple application instances can share a single model server
- 3.4 Model server supports GPU acceleration (optional, for future)

### 4. Graceful Degradation
**As a** user  
**I want** the application to remain functional when models are loading  
**So that** I can still use basic features during startup

#### Acceptance Criteria
- 4.1 Application returns appropriate fallback responses when model server unavailable
- 4.2 Application retries model server connection with exponential backoff
- 4.3 Health check indicates degraded status when model server unavailable
- 4.4 Application logs clear messages about model server connectivity

## Technical Requirements

### Model Server Container
- Python FastAPI service
- Loads sentence-transformers models (all-MiniLM-L6-v2)
- Loads spacy models (en_core_web_sm)
- Exposes gRPC or REST API for inference
- Health check endpoint with model loading status
- Configurable model list via environment variables

### Application Container Changes
- Remove direct model loading code
- Add model server client for inference calls
- Implement connection pooling and retry logic
- Support fallback behavior when model server unavailable

### Docker Compose Integration
- New `model-server` service definition
- Proper dependency ordering (model-server starts before app)
- Shared network for inter-container communication
- Volume mounts for model caching (optional)

## Out of Scope
- GPU support (future enhancement)
- Model versioning and A/B testing
- Distributed model serving (e.g., Ray Serve)
- Custom model training endpoints
