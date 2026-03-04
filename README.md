# Multimodal Librarian

A conversational web-based knowledge management system that processes PDF books with multimodal content, stores them in a unified vector database, and enables conversational queries with multimedia output generation.

## Features

- **Multimodal PDF Processing**: Extract text, images, charts, and metadata from PDF files
- **Generic Multi-Level Chunking Framework**: Automated content profiling and adaptive chunking strategies
- **Unified Knowledge Management**: Treat books and conversations as equivalent knowledge sources
- **Conversational Interface**: Multimedia chat interface with real-time interactions
- **Knowledge Graph Integration**: Concept extraction and multi-hop reasoning capabilities
- **Multimedia Output Generation**: Generate text, charts, audio, and video responses
- **Multi-Format Export**: Export to .txt, .docx, .pdf, .rtf, .pptx, and .xlsx formats
- **ML Training APIs**: Streaming access to knowledge chunks for reinforcement learning

## Quick Start

### Environment Setup

The Multimodal Librarian supports two environments:

- **Local Development**: Docker Compose with local services (recommended for development)
- **AWS Production**: AWS-managed services (Neptune, OpenSearch, RDS)

#### Local Development Setup

1. **Create environment configuration**:
   ```bash
   cp .env.local.example .env.local
   ```

2. **Add your API keys** (required for AI functionality):
   ```bash
   # Edit .env.local and add:
   OPENAI_API_KEY=your-openai-api-key-here
   GOOGLE_API_KEY=your-google-api-key-here
   GEMINI_API_KEY=your-gemini-api-key-here
   ```

3. **Start local services**:
   ```bash
   make dev-local
   ```

4. **Verify setup**:
   ```bash
   python scripts/switch-environment.py status
   curl http://localhost:8000/health/simple
   ```

#### Environment Switching

Use the environment switcher for easy switching between environments:

```bash
# Switch to local development
python scripts/switch-environment.py switch local

# Switch to AWS production  
python scripts/switch-environment.py switch aws

# Check current environment
python scripts/switch-environment.py status

# Validate environment configuration
python scripts/switch-environment.py validate local
```

For detailed setup instructions, see [Environment Setup Guide](docs/environment-setup-guide.md).

## Architecture

The system follows a microservices approach with the following components:

- **Model Server**: Dedicated service for ML model inference (embeddings, NLP)
- **PDF Processing Component**: Extracts multimodal content from PDF files
- **Multi-Level Chunking Framework**: Adaptive chunking with smart bridge generation
- **Vector Database Component**: Unified storage for all knowledge sources
- **Conversation Management**: Real-time chat with knowledge integration
- **Knowledge Graph Builder**: Concept extraction and relationship discovery
- **Query Processing**: Unified search across all knowledge sources
- **Multimedia Generation**: Multi-format content generation
- **Export Engine**: Multi-format export capabilities

### Dependency Injection Architecture

The application uses FastAPI's native dependency injection system for all service and component management. This ensures:

- **Fast Startup**: No blocking initialization during module import
- **Testability**: All services can be mocked using `app.dependency_overrides`
- **Graceful Degradation**: Optional dependencies allow endpoints to function with reduced capabilities
- **Clean Lifecycle**: Proper cleanup of all connections during shutdown

#### Key Patterns

```python
from fastapi import Depends
from multimodal_librarian.api.dependencies import get_ai_service, get_rag_service

@router.post("/chat")
async def chat(
    message: str,
    ai_service = Depends(get_ai_service),      # Required dependency
    rag_service = Depends(get_rag_service)     # Returns None if unavailable
):
    if rag_service:
        return await rag_service.query(message)
    return await ai_service.generate(message)
```

#### Available Dependencies

| Category | Dependencies |
|----------|-------------|
| AI/LLM | `get_ai_service`, `get_cached_ai_service_di` |
| RAG | `get_rag_service`, `get_cached_rag_service` |
| Vector DB | `get_opensearch_client`, `get_vector_store` |
| Search | `get_search_service`, `get_query_processor` |
| WebSocket | `get_connection_manager`, `get_connection_manager_with_services` |

For detailed documentation, see:
- [DI Steering Guide](.kiro/steering/dependency-injection.md)
- [Adding New Services](docs/architecture/adding-new-services-with-di.md)

### Model Server

The Model Server is a dedicated microservice that handles ML model inference, separating heavy model loading from the main application. This improves startup time and allows independent scaling.

#### Features

- **Embedding Generation**: Generate text embeddings using sentence-transformers
- **NLP Processing**: Tokenization, NER, and POS tagging using spaCy
- **Health Monitoring**: Dedicated health endpoints for model status
- **Graceful Degradation**: App continues to function when model server is unavailable

#### Configuration

The model server is configured via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_SERVER_URL` | `http://model-server:8001` | Model server URL |
| `MODEL_SERVER_ENABLED` | `true` | Enable/disable model server |
| `MODEL_SERVER_TIMEOUT` | `30.0` | Request timeout in seconds |

#### Running the Model Server

With Docker Compose (recommended):
```bash
docker compose up model-server
```

Standalone:
```bash
uvicorn src.model_server.main:app --host 0.0.0.0 --port 8001
```

#### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Model server health status |
| `/health/ready` | GET | Readiness probe |
| `/health/live` | GET | Liveness probe |
| `/embeddings` | POST | Generate text embeddings |
| `/nlp/process` | POST | Process text with NLP tasks |

For detailed documentation, see [DOCKER.md](DOCKER.md#model-server).

## Installation

### Prerequisites

- Python 3.9 or higher
- PostgreSQL database
- Milvus vector database
- (Optional) Neo4j for knowledge graph features

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd multimodal-librarian
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Initialize the database:
```bash
# TODO: Add database initialization commands
```

6. Run the application:
```bash
python -m multimodal_librarian.main
```

## Local Development Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.9+
- 8GB+ RAM recommended
- 20GB+ free disk space

### Quick Start

1. **Clone and setup environment**:
   ```bash
   git clone <repository>
   cd multimodal-librarian
   cp .env.local.example .env.local
   # Edit .env.local with your API keys
   ```

2. **Start local development environment**:
   ```bash
   make dev-local
   # Or manually:
   docker-compose -f docker-compose.local.yml up -d
   ```

3. **Verify setup**:
   ```bash
   # Check all services are running
   docker-compose -f docker-compose.local.yml ps
   
   # Validate PostgreSQL setup
   python database/postgresql/validate_setup.py
   
   # Check application health
   curl http://localhost:8000/health/simple
   ```

4. **Access services**:
   - **Application**: http://localhost:8000
   - **API Documentation**: http://localhost:8000/docs
   - **PostgreSQL**: localhost:5432 (ml_user/ml_password)
   - **Neo4j Browser**: http://localhost:7474 (neo4j/ml_password)
   - **pgAdmin**: http://localhost:5050 (admin@multimodal-librarian.local/admin)
   - **Milvus Admin (Attu)**: http://localhost:3000
   - **Redis Commander**: http://localhost:8081

### Database Management

The local setup includes comprehensive PostgreSQL management tools:

```bash
# Database status and health
make db-status
make health

# Database maintenance
make db-maintenance

# Backup and restore
make backup           # Create full backup
make backup-all       # Create all backup types
make restore          # Restore from latest backup

# Database shell access
make db-shell

# Reset database (DANGEROUS!)
make db-reset
```

### Development Workflow

1. **Code changes**: Edit files in `src/` - hot reload is enabled
2. **Database changes**: Use migrations in `src/multimodal_librarian/database/migrations/`
3. **Testing**: Run `pytest` against local services
4. **Debugging**: Use `make logs` to view service logs

### Service Configuration

All services are configured for local development with:
- **PostgreSQL 15**: Optimized for development, includes monitoring and maintenance tools
- **Neo4j Community**: Knowledge graph with APOC and GDS plugins
- **Milvus**: Vector similarity search with MinIO and etcd
- **Redis**: Caching layer
- **Administration tools**: pgAdmin, Neo4j Browser, Attu, Redis Commander

### Environment Variables

Key environment variables in `.env.local`:
```bash
# Database configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=multimodal_librarian
POSTGRES_USER=ml_user
POSTGRES_PASSWORD=ml_password

# API Keys (set these for full functionality)
OPENAI_API_KEY=your_openai_key
GOOGLE_API_KEY=your_google_key
GEMINI_API_KEY=your_gemini_key
```

### Troubleshooting

Common issues and solutions:

1. **Services won't start**:
   ```bash
   docker-compose -f docker-compose.local.yml down -v
   docker-compose -f docker-compose.local.yml up -d
   ```

2. **Database connection issues**:
   ```bash
   # Check PostgreSQL health
   ./database/postgresql/manage.sh health
   
   # Validate setup
   python database/postgresql/validate_setup.py
   ```

3. **Performance issues**:
   ```bash
   # Check resource usage
   make monitor
   
   # Run database maintenance
   make db-maintenance
   ```

4. **Reset everything**:
   ```bash
   make clean-docker
   make dev-local
   ```

## Development

### Project Structure

```
src/multimodal_librarian/
├── __init__.py
├── main.py                 # FastAPI application
├── config.py              # Configuration management
├── logging_config.py      # Logging setup
├── api/                   # API endpoints and routers
├── components/            # Core processing components
│   ├── pdf_processor/     # PDF processing
│   ├── chunking_framework/ # Multi-level chunking
│   ├── vector_store/      # Vector database management
│   ├── conversation/      # Conversation management
│   ├── knowledge_graph/   # Knowledge graph building
│   ├── query_processor/   # Query processing
│   ├── multimedia_generator/ # Multimedia generation
│   └── export_engine/     # Export functionality
├── models/                # Data models and schemas
├── database/              # Database management
└── utils/                 # Utility functions

tests/                     # Test suite
├── components/            # Component tests
├── api/                   # API tests
└── conftest.py           # Test configuration
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=multimodal_librarian

# Run specific test file
pytest tests/components/test_pdf_processor.py
```

### Code Quality

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

## Configuration

The application uses environment variables for configuration. See `.env.example` for all available options.

Key configuration areas:
- Database connections (PostgreSQL, Milvus, Neo4j)
- External API keys (OpenAI, Google)
- File storage directories
- Processing parameters
- Security settings

## API Documentation

Once the application is running, visit:
- API Documentation: http://localhost:8000/docs
- Alternative Documentation: http://localhost:8000/redoc

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.