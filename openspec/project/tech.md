# Technology Stack

## Core Framework

- **Python 3.9+**: Primary language
- **FastAPI 0.104+**: Web framework with async support
- **Uvicorn**: ASGI server
- **Pydantic 2.5+**: Data validation and settings management

## Databases

- **Neo4j**: Graph database for knowledge graph operations (Cypher queries, Docker)
- **Milvus**: Vector database for semantic search and embeddings (Docker)
- **PostgreSQL 15**: Relational database for metadata and configuration

## ML & NLP

- **sentence-transformers**: Text embeddings
- **torch**: Deep learning framework
- **transformers**: Hugging Face models
- **spacy**: NLP processing
- **scikit-learn**: ML utilities

## PDF Processing

- **PyMuPDF**: PDF parsing
- **pdfplumber**: Text extraction
- **Pillow**: Image processing
- **pytesseract**: OCR capabilities

## External APIs

- **OpenAI**: Text generation and embeddings
- **Google Gemini**: Bridge generation
- **Anthropic**: Alternative LLM provider

## Infrastructure

- **Docker**: Containerization
- **Terraform**: Infrastructure as code (AWS)
- **AWS ECS Fargate**: Container orchestration
- **AWS ALB**: Load balancing
- **AWS CloudFront**: CDN (optional)

## Monitoring & Logging

- **structlog**: Structured logging
- **CloudWatch**: AWS monitoring and logs
- **Custom metrics**: Performance tracking and alerting

## Security

- **PyJWT**: JWT token handling
- **cryptography**: Encryption utilities
- **passlib**: Password hashing
- **AWS KMS**: Key management
- **AWS Secrets Manager**: Secrets storage

## Build System

### Development Commands

```bash
# Setup
make setup              # Complete development setup
make dev-install        # Install dependencies

# Running
make dev                # Start development environment (Docker)
make run                # Run locally without Docker

# Testing
make test               # Run tests locally
make test-docker        # Run tests in Docker
make test-cov           # Run tests with coverage

# Code Quality
make format             # Format code (black, isort)
make lint               # Run linting (flake8)
make type-check         # Run type checking (mypy)
make quality            # Run all quality checks

# Docker Operations
make up                 # Start all services
make down               # Stop all services
make logs               # View service logs
make shell              # Open shell in app container

# Production
make prod               # Start production environment
make prod-deploy        # Deploy to production

# Maintenance
make clean              # Clean generated files
make clean-docker       # Clean Docker resources
make backup             # Backup databases
make health             # Check service health
make monitor            # Show resource usage
```

### Testing Commands

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/components/test_pdf_processor.py

# Run with coverage
pytest --cov=multimodal_librarian --cov-report=html

# Run integration tests
pytest tests/integration/

# Run performance tests
pytest tests/performance/
```

### Deployment Commands

```bash
# AWS Deployment (Terraform)
cd infrastructure/aws-native
terraform init
terraform plan
terraform apply

# Docker Build
docker-compose build
docker-compose up -d

# Health Check
curl http://localhost:8000/health/simple
```

## Configuration

- **Environment Variables**: `.env` file for configuration
- **Pydantic Settings**: Type-safe configuration management
- **AWS Secrets Manager**: Production secrets
- **Hot Reload**: Configuration updates without restart (development)

## Key Dependencies

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
sentence-transformers>=2.2.0
torch>=2.1.0
transformers>=4.35.0
psycopg2-binary==2.9.9
boto3==1.34.0
neo4j>=5.0.0
pymilvus>=2.3.0
PyMuPDF==1.23.8
```

See `requirements.txt` for complete dependency list.
