# Project Structure

## Root Directory

```
multimodal-librarian/
├── src/multimodal_librarian/    # Main application code
├── tests/                        # Test suite
├── infrastructure/               # Infrastructure as code
├── scripts/                      # Deployment and utility scripts
├── docs/                         # Documentation
├── .kiro/                        # Kiro specs and steering
├── docker-compose.yml            # Docker orchestration
├── Dockerfile                    # Container definition
├── Makefile                      # Build automation
├── requirements.txt              # Python dependencies
└── pyproject.toml               # Project metadata
```

## Source Code Organization

```
src/multimodal_librarian/
├── main.py                      # Application entry point
├── config.py                    # Configuration management
├── logging_config.py            # Logging setup
│
├── api/                         # API layer
│   ├── routers/                 # FastAPI route handlers
│   ├── middleware/              # Request/response middleware
│   ├── models/                  # API request/response models
│   └── dependencies/            # Dependency injection
│
├── components/                  # Core processing components
│   ├── pdf_processor/           # PDF extraction and parsing
│   ├── chunking_framework/      # Adaptive chunking system
│   ├── vector_store/            # Vector database operations
│   ├── knowledge_graph/         # Graph database operations
│   ├── conversation/            # Conversation management
│   ├── query_processor/         # Query processing and synthesis
│   ├── document_manager/        # Document lifecycle management
│   ├── multimedia_generator/    # Multimedia output generation
│   └── export_engine/           # Multi-format export
│
├── services/                    # Business logic services
│   ├── ai_service.py            # AI/LLM integration
│   ├── chat_service.py          # Chat functionality
│   ├── rag_service.py           # RAG implementation
│   ├── analytics_service.py     # Analytics and metrics
│   ├── cache_service.py         # Caching layer
│   └── storage_service.py       # File storage
│
├── models/                      # Data models and schemas
│   ├── core.py                  # Core domain models
│   ├── documents.py             # Document models
│   ├── knowledge_graph.py       # Graph models
│   └── search.py                # Search models
│
├── database/                    # Database layer
│   ├── connection.py            # Database connections
│   ├── models.py                # SQLAlchemy models
│   ├── migrations/              # Database migrations
│   └── init_db.sql              # Initial schema
│
├── clients/                     # External service clients
│   ├── neptune_client.py        # AWS Neptune client
│   ├── opensearch_client.py     # AWS OpenSearch client
│   └── database_factory.py      # Database client factory
│
├── startup/                     # Application startup
│   ├── phase_manager.py         # Startup phase orchestration
│   ├── progressive_loader.py    # Progressive model loading
│   ├── minimal_server.py        # Fast startup server
│   └── async_database_init.py   # Async DB initialization
│
├── monitoring/                  # Observability
│   ├── health_check_system.py   # Health checks
│   ├── metrics_collector.py     # Metrics collection
│   ├── alerting_service.py      # Alert management
│   ├── performance_tracker.py   # Performance monitoring
│   └── startup_metrics.py       # Startup metrics
│
├── logging/                     # Logging infrastructure
│   ├── startup_logger.py        # Startup logging
│   ├── ux_logger.py             # User experience logging
│   └── log_aggregator.py        # Log aggregation
│
├── security/                    # Security features
│   ├── auth.py                  # Authentication
│   ├── encryption.py            # Encryption utilities
│   ├── audit.py                 # Audit logging
│   └── rate_limiter.py          # Rate limiting
│
├── validation/                  # Deployment validation
│   ├── checklist_validator.py   # Pre-deployment checks
│   ├── network_config_validator.py
│   └── cli.py                   # Validation CLI
│
├── aws/                         # AWS integrations
│   ├── s3_simple.py             # S3 operations
│   ├── secrets_manager_basic.py # Secrets management
│   └── cloudwatch_logger_basic.py
│
├── utils/                       # Utility functions
│   ├── memory_manager.py        # Memory management
│   └── model_request_wrapper.py # Model request handling
│
├── static/                      # Static web assets
│   ├── css/                     # Stylesheets
│   ├── js/                      # JavaScript
│   └── index.html               # Main web interface
│
└── templates/                   # HTML templates
    ├── documents.html           # Document management UI
    ├── analytics_dashboard.html # Analytics UI
    └── loading.html             # Loading states
```

## Test Organization

```
tests/
├── components/                  # Component tests
├── integration/                 # Integration tests
├── performance/                 # Performance tests
├── security/                    # Security tests
├── infrastructure/              # Infrastructure tests
├── startup/                     # Startup tests
├── ux/                         # User experience tests
└── conftest.py                 # Pytest configuration
```

## Infrastructure

```
infrastructure/
└── aws-native/                  # AWS Terraform modules
    ├── main.tf                  # Main infrastructure
    ├── variables.tf             # Input variables
    ├── outputs.tf               # Output values
    ├── modules/
    │   ├── vpc/                 # Network infrastructure
    │   ├── security/            # Security groups, IAM
    │   ├── databases/           # Neptune, OpenSearch
    │   ├── application/         # ECS, ALB, CloudFront
    │   ├── monitoring/          # CloudWatch, alerts
    │   ├── backup/              # Backup infrastructure
    │   └── cost_optimization/   # Cost management
    └── lambda/                  # Lambda functions
```

## Scripts

```
scripts/
├── deploy-*.py                  # Deployment scripts
├── diagnose-*.py                # Diagnostic scripts
├── fix-*.py                     # Fix scripts
├── test-*.py                    # Test scripts
└── rebuild-and-redeploy.py      # Full rebuild
```

## Documentation

```
docs/
├── architecture/                # Architecture documentation
├── api/                         # API documentation
├── deployment/                  # Deployment guides
├── operations/                  # Operations guides
├── troubleshooting/             # Troubleshooting guides
└── user-guide/                  # User documentation
```

## Specs

```
.kiro/specs/                     # Feature specifications
├── multimodal-librarian/        # Core feature spec
├── aws-deployment/              # AWS deployment spec
├── application-health-startup-optimization/
├── chat-and-document-integration/
└── [other feature specs]/
```

## Database Tables

PostgreSQL tables (schema: `multimodal_librarian`):

| Table | Description |
|-------|-------------|
| `knowledge_sources` | Uploaded documents |
| `knowledge_chunks` | Chunk metadata with source type and references |
| `bridge_chunks` | LLM-generated bridge chunks connecting adjacent chunks |
| `processing_jobs` | Celery job tracking |
| `enrichment_status` | Background enrichment metrics |
| `conversation_threads` | Chat conversation threads |
| `messages` | Chat messages |
| `user_sessions` | User session data |
| `users` | User accounts |
| `domain_configurations` | Domain-specific configurations |
| `export_history` | Document export history |
| `performance_metrics` | Performance tracking data |
| `user_feedback` | User feedback records |

## Key Conventions

- **Module naming**: Snake case (e.g., `pdf_processor.py`)
- **Class naming**: Pascal case (e.g., `PDFProcessor`)
- **Function naming**: Snake case (e.g., `process_document()`)
- **Constants**: Upper snake case (e.g., `MAX_FILE_SIZE`)
- **Async functions**: Prefix with `async def`
- **Private functions**: Prefix with underscore (e.g., `_internal_helper()`)
- **Test files**: Prefix with `test_` (e.g., `test_pdf_processor.py`)
- **Router files**: Named by domain (e.g., `chat.py`, `documents.py`)
- **Service files**: Suffix with `_service` (e.g., `chat_service.py`)
