# Model Server Separation Design

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Docker Compose Network                       │
│                                                                  │
│  ┌──────────────────┐         ┌──────────────────────────────┐  │
│  │   App Container  │         │    Model Server Container    │  │
│  │                  │  HTTP   │                              │  │
│  │  ┌────────────┐  │ ──────► │  ┌────────────────────────┐  │  │
│  │  │ Model      │  │         │  │  Embedding Models      │  │  │
│  │  │ Client     │  │         │  │  - all-MiniLM-L6-v2    │  │  │
│  │  └────────────┘  │         │  └────────────────────────┘  │  │
│  │                  │         │                              │  │
│  │  ┌────────────┐  │         │  ┌────────────────────────┐  │  │
│  │  │ FastAPI    │  │         │  │  NLP Models            │  │  │
│  │  │ App        │  │         │  │  - en_core_web_sm      │  │  │
│  │  └────────────┘  │         │  └────────────────────────┘  │  │
│  │                  │         │                              │  │
│  └──────────────────┘         │  ┌────────────────────────┐  │  │
│                               │  │  FastAPI Server        │  │  │
│                               │  │  - /embeddings         │  │  │
│                               │  │  - /nlp/tokenize       │  │  │
│                               │  │  - /nlp/ner            │  │  │
│                               │  │  - /health             │  │  │
│                               │  └────────────────────────┘  │  │
│                               └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Design

### 1. Model Server Service

**Location**: `src/model_server/`

```
src/model_server/
├── __init__.py
├── main.py              # FastAPI application
├── models/
│   ├── __init__.py
│   ├── embedding.py     # Embedding model wrapper
│   └── nlp.py           # NLP model wrapper (spacy)
├── api/
│   ├── __init__.py
│   ├── embeddings.py    # Embedding endpoints
│   ├── nlp.py           # NLP endpoints
│   └── health.py        # Health check endpoints
└── config.py            # Configuration
```

#### API Endpoints

**POST /embeddings**
```json
Request:
{
  "texts": ["text1", "text2", ...],
  "model": "all-MiniLM-L6-v2"  // optional, default model
}

Response:
{
  "embeddings": [[0.1, 0.2, ...], [0.3, 0.4, ...]],
  "model": "all-MiniLM-L6-v2",
  "dimensions": 384,
  "processing_time_ms": 45
}
```

**POST /nlp/process**
```json
Request:
{
  "texts": ["text1", "text2"],
  "tasks": ["tokenize", "ner", "pos"]
}

Response:
{
  "results": [
    {
      "text": "text1",
      "tokens": ["token1", "token2"],
      "entities": [{"text": "...", "label": "ORG", "start": 0, "end": 5}],
      "pos_tags": [{"token": "...", "pos": "NOUN"}]
    }
  ],
  "processing_time_ms": 30
}
```

**GET /health**
```json
Response:
{
  "status": "healthy",
  "models": {
    "embedding": {
      "name": "all-MiniLM-L6-v2",
      "status": "loaded",
      "load_time_seconds": 2.5
    },
    "nlp": {
      "name": "en_core_web_sm",
      "status": "loaded",
      "load_time_seconds": 1.2
    }
  },
  "ready": true
}
```

### 2. Model Client (App Side)

**Location**: `src/multimodal_librarian/clients/model_server_client.py`

```python
class ModelServerClient:
    """Client for communicating with the model server."""
    
    def __init__(
        self,
        base_url: str = "http://model-server:8001",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._session: Optional[aiohttp.ClientSession] = None
        self._healthy = False
    
    async def generate_embeddings(
        self, 
        texts: List[str],
        model: str = "all-MiniLM-L6-v2"
    ) -> List[List[float]]:
        """Generate embeddings via model server."""
        ...
    
    async def process_nlp(
        self,
        texts: List[str],
        tasks: List[str] = ["tokenize", "ner"]
    ) -> List[Dict]:
        """Process NLP tasks via model server."""
        ...
    
    async def health_check(self) -> Dict:
        """Check model server health."""
        ...
    
    async def wait_for_ready(
        self, 
        timeout: float = 120.0,
        poll_interval: float = 2.0
    ) -> bool:
        """Wait for model server to be ready."""
        ...
```

### 3. Docker Compose Configuration

```yaml
services:
  model-server:
    build:
      context: .
      dockerfile: Dockerfile.model-server
    ports:
      - "8001:8001"
    environment:
      - EMBEDDING_MODEL=all-MiniLM-L6-v2
      - NLP_MODEL=en_core_web_sm
      - LOG_LEVEL=INFO
    volumes:
      - model-cache:/root/.cache  # Cache downloaded models
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 60s  # Allow time for model loading
    deploy:
      resources:
        limits:
          memory: 2G

  app:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      model-server:
        condition: service_healthy
    environment:
      - MODEL_SERVER_URL=http://model-server:8001
      - MODEL_SERVER_TIMEOUT=30
    # ... rest of app config

volumes:
  model-cache:
```

### 4. Dockerfile for Model Server

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements-model-server.txt .
RUN pip install --no-cache-dir -r requirements-model-server.txt

# Download models at build time (optional, for faster startup)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
RUN python -c "import spacy; spacy.cli.download('en_core_web_sm')"

# Copy application code
COPY src/model_server /app/src/model_server

# Run server
CMD ["uvicorn", "src.model_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

## Integration Points

### Embedding Generation
Current code in `vector_store_optimized.py` and `ai_service.py` that loads models directly will be refactored to use `ModelServerClient`.

**Before:**
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(texts)
```

**After:**
```python
from ..clients.model_server_client import get_model_client
client = await get_model_client()
embeddings = await client.generate_embeddings(texts)
```

### NLP Processing
Current code in `model_manager.py` that loads spacy will use the model server.

**Before:**
```python
import spacy
nlp = spacy.load("en_core_web_sm")
doc = nlp(text)
```

**After:**
```python
client = await get_model_client()
result = await client.process_nlp([text], tasks=["tokenize", "ner"])
```

## Fallback Behavior

When model server is unavailable:

1. **Embedding requests**: Return error with clear message, or use cached embeddings if available
2. **NLP requests**: Return basic tokenization using Python's built-in tokenizer
3. **Health check**: Report degraded status with details about model server connectivity

## Configuration

Environment variables for the app:
- `MODEL_SERVER_URL`: URL of model server (default: `http://model-server:8001`)
- `MODEL_SERVER_TIMEOUT`: Request timeout in seconds (default: `30`)
- `MODEL_SERVER_RETRIES`: Number of retry attempts (default: `3`)
- `MODEL_SERVER_ENABLED`: Enable/disable model server (default: `true`)

Environment variables for model server:
- `EMBEDDING_MODEL`: Embedding model to load (default: `all-MiniLM-L6-v2`)
- `NLP_MODEL`: Spacy model to load (default: `en_core_web_sm`)
- `PORT`: Server port (default: `8001`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

## Correctness Properties

### Property 1: Embedding Consistency
For any text input, embeddings generated by the model server must be identical to embeddings that would be generated by loading the model directly.

### Property 2: Graceful Degradation
When the model server is unavailable, the application must:
- Continue responding to health checks
- Return appropriate error responses for model-dependent endpoints
- Not crash or hang indefinitely

### Property 3: Connection Resilience
The model client must handle transient network failures with retry logic and not leak connections.

### Property 4: Startup Independence
The application container must start and pass health checks without waiting for the model server to be fully ready.
