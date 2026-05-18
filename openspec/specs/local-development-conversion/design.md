# Local Development Conversion Design

## Architecture Overview

The local development conversion maintains the same application architecture while replacing AWS-native databases with local alternatives orchestrated via Docker Compose.

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│                 Dependency Injection Layer                  │
├─────────────────────────────────────────────────────────────┤
│              Database Client Factory                        │
├─────────────────────────────────────────────────────────────┤
│  Neo4j Client  │  Milvus Client  │  PostgreSQL Client      │
├─────────────────────────────────────────────────────────────┤
│     Neo4j      │     Milvus      │    PostgreSQL           │
│   (Docker)     │   (Docker)      │     (Docker)            │
└─────────────────────────────────────────────────────────────┘
```

## Database Mapping Strategy

### 1. AWS Neptune → Neo4j

**Current State:**
- AWS Neptune with Gremlin queries
- Graph-based knowledge representation
- Managed service with automatic scaling

**Target State:**
- Neo4j Community Edition in Docker
- Cypher queries (with Gremlin compatibility layer if needed)
- Local instance with manual configuration

**Migration Strategy:**
```python
# Current Neptune client
class NeptuneClient:
    def __init__(self, endpoint: str):
        self.client = gremlin_python.driver.client.Client(endpoint)
    
    def execute_query(self, query: str):
        return self.client.submit(query).all().result()

# New Neo4j client with same interface
class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    
    def execute_query(self, query: str):
        # Convert Gremlin to Cypher or use neo4j-gremlin plugin
        with self.driver.session() as session:
            return session.run(query).data()
```

### 2. AWS OpenSearch → Milvus

**Current State:**
- AWS OpenSearch for vector similarity search
- Elasticsearch-compatible API
- Managed indexing and search

**Target State:**
- Milvus standalone for vector operations
- Native vector similarity search
- Local instance with manual management

**Migration Strategy:**
```python
# Current OpenSearch client
class OpenSearchClient:
    def __init__(self, endpoint: str):
        self.client = OpenSearch([endpoint])
    
    def search_vectors(self, vector: List[float], k: int):
        return self.client.search(body={
            "query": {"knn": {"vector_field": {"vector": vector, "k": k}}}
        })

# New Milvus client with same interface
class MilvusClient:
    def __init__(self, host: str, port: int):
        self.client = connections.connect(host=host, port=port)
    
    def search_vectors(self, vector: List[float], k: int):
        collection = Collection("documents")
        return collection.search([vector], "embeddings", {"metric_type": "L2"}, k)
```

### 3. AWS RDS PostgreSQL → Local PostgreSQL

**Current State:**
- AWS RDS PostgreSQL for metadata and configuration
- Managed backups and scaling
- Connection pooling via RDS Proxy

**Target State:**
- PostgreSQL 15 in Docker
- Local connection pooling via pgbouncer
- Manual backup management

**Migration Strategy:**
```python
# Database factory pattern (already exists)
class DatabaseFactory:
    @staticmethod
    def create_postgres_client(config: DatabaseConfig):
        if config.environment == "local":
            return LocalPostgreSQLClient(config.local_connection_string)
        else:
            return AWSPostgreSQLClient(config.aws_connection_string)
```

## Docker Compose Architecture

### Service Definitions

```yaml
version: '3.8'

services:
  # Application
  multimodal-librarian:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_TYPE=local
      - POSTGRES_HOST=postgres
      - NEO4J_HOST=neo4j
      - MILVUS_HOST=milvus
    depends_on:
      postgres:
        condition: service_healthy
      neo4j:
        condition: service_healthy
      milvus:
        condition: service_healthy
    volumes:
      - ./uploads:/app/uploads
      - ./logs:/app/logs

  # PostgreSQL for metadata and configuration
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: multimodal_librarian
      POSTGRES_USER: ml_user
      POSTGRES_PASSWORD: ml_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init_db.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ml_user -d multimodal_librarian"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Neo4j for knowledge graph
  neo4j:
    image: neo4j:5.15-community
    environment:
      NEO4J_AUTH: neo4j/ml_password
      NEO4J_PLUGINS: '["gds", "apoc"]'
      NEO4J_dbms_security_procedures_unrestricted: gds.*,apoc.*
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "ml_password", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Milvus for vector similarity search
  milvus:
    image: milvusdb/milvus:v2.3.4
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
    depends_on:
      - etcd
      - minio
    volumes:
      - milvus_data:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      timeout: 20s
      retries: 3

  # Milvus dependencies
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd

  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    ports:
      - "9001:9001"
    volumes:
      - minio_data:/data
    command: minio server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  # Database administration tools
  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@multimodal-librarian.com
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres

  # Milvus administration
  attu:
    image: zilliz/attu:v2.3.4
    environment:
      MILVUS_URL: milvus:19530
    ports:
      - "3000:3000"
    depends_on:
      - milvus

volumes:
  postgres_data:
  neo4j_data:
  neo4j_logs:
  milvus_data:
  etcd_data:
  minio_data:
```

## Configuration Management

### Environment Configuration

```python
# src/multimodal_librarian/config/local_config.py
from pydantic import BaseSettings
from typing import Literal

class LocalDatabaseConfig(BaseSettings):
    # Environment selection
    database_type: Literal["local", "aws"] = "local"
    
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "multimodal_librarian"
    postgres_user: str = "ml_user"
    postgres_password: str = "ml_password"
    
    # Neo4j
    neo4j_host: str = "localhost"
    neo4j_port: int = 7687
    neo4j_user: str = "neo4j"
    neo4j_password: str = "ml_password"
    
    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    
    class Config:
        env_file = ".env.local"
        env_prefix = "ML_"

# src/multimodal_librarian/config/config_factory.py
def get_database_config() -> DatabaseConfig:
    env = os.getenv("ML_ENVIRONMENT", "local")
    
    if env == "local":
        return LocalDatabaseConfig()
    elif env == "aws":
        return AWSNativeConfig()
    else:
        raise ValueError(f"Unknown environment: {env}")
```

### Database Client Factory

```python
# src/multimodal_librarian/clients/database_factory.py
from typing import Protocol

class VectorStoreClient(Protocol):
    def search_vectors(self, vector: List[float], k: int) -> List[dict]: ...
    def insert_vectors(self, vectors: List[dict]) -> bool: ...

class GraphStoreClient(Protocol):
    def execute_query(self, query: str) -> List[dict]: ...
    def create_node(self, labels: List[str], properties: dict) -> str: ...

class DatabaseClientFactory:
    def __init__(self, config: DatabaseConfig):
        self.config = config
    
    def create_vector_store_client(self) -> VectorStoreClient:
        if self.config.database_type == "local":
            return MilvusClient(
                host=self.config.milvus_host,
                port=self.config.milvus_port
            )
        else:
            return OpenSearchClient(
                endpoint=self.config.opensearch_endpoint
            )
    
    def create_graph_store_client(self) -> GraphStoreClient:
        if self.config.database_type == "local":
            return Neo4jClient(
                uri=f"bolt://{self.config.neo4j_host}:{self.config.neo4j_port}",
                user=self.config.neo4j_user,
                password=self.config.neo4j_password
            )
        else:
            return NeptuneClient(
                endpoint=self.config.neptune_endpoint
            )
    
    def create_postgres_client(self) -> PostgreSQLClient:
        if self.config.database_type == "local":
            return LocalPostgreSQLClient(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_db,
                user=self.config.postgres_user,
                password=self.config.postgres_password
            )
        else:
            return AWSPostgreSQLClient(
                endpoint=self.config.rds_endpoint,
                credentials=self.config.rds_credentials
            )
```

## Development Workflow Integration

### Makefile Updates

```makefile
# Local development targets
.PHONY: dev-local dev-aws dev-setup dev-teardown

dev-local: dev-setup
	@echo "Starting local development environment..."
	docker-compose -f docker-compose.local.yml up -d
	@echo "Waiting for services to be ready..."
	./scripts/wait-for-services.sh
	@echo "Local development environment ready!"
	@echo "Application: http://localhost:8000"
	@echo "Neo4j Browser: http://localhost:7474"
	@echo "pgAdmin: http://localhost:5050"
	@echo "Attu (Milvus): http://localhost:3000"

dev-aws:
	@echo "Starting AWS development environment..."
	export ML_ENVIRONMENT=aws
	uvicorn src.multimodal_librarian.main:app --reload --host 0.0.0.0 --port 8000

dev-setup:
	@echo "Setting up local development environment..."
	cp .env.local.example .env.local
	docker-compose -f docker-compose.local.yml pull

dev-teardown:
	@echo "Tearing down local development environment..."
	docker-compose -f docker-compose.local.yml down -v
	docker system prune -f

# Testing with local services
test-local:
	@echo "Running tests against local services..."
	export ML_ENVIRONMENT=local
	pytest tests/ -v

# Database management
db-migrate-local:
	@echo "Running database migrations for local environment..."
	export ML_ENVIRONMENT=local
	python -m src.multimodal_librarian.database.migrations

db-seed-local:
	@echo "Seeding local databases with test data..."
	export ML_ENVIRONMENT=local
	python scripts/seed-local-data.py

# Monitoring and debugging
logs-local:
	docker-compose -f docker-compose.local.yml logs -f

status-local:
	docker-compose -f docker-compose.local.yml ps
```

### Service Health Checks

```python
# scripts/wait-for-services.sh
#!/bin/bash

echo "Waiting for PostgreSQL..."
until docker-compose -f docker-compose.local.yml exec postgres pg_isready -U ml_user -d multimodal_librarian; do
  sleep 2
done

echo "Waiting for Neo4j..."
until docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password "RETURN 1"; do
  sleep 2
done

echo "Waiting for Milvus..."
until curl -f http://localhost:19530/healthz; do
  sleep 2
done

echo "All services are ready!"
```

## Data Seeding Strategy

### Sample Data Generation

```python
# scripts/seed-local-data.py
import asyncio
from src.multimodal_librarian.clients.database_factory import DatabaseClientFactory
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig

async def seed_postgres_data(client):
    """Seed PostgreSQL with sample users, documents, conversations."""
    await client.execute("""
        INSERT INTO users (id, email, name) VALUES 
        ('user1', 'dev@example.com', 'Developer User'),
        ('user2', 'test@example.com', 'Test User');
    """)
    
    await client.execute("""
        INSERT INTO documents (id, title, filename, user_id) VALUES
        ('doc1', 'Sample Document', 'sample.pdf', 'user1'),
        ('doc2', 'Test Document', 'test.pdf', 'user2');
    """)

async def seed_neo4j_data(client):
    """Seed Neo4j with sample knowledge graph."""
    await client.execute_query("""
        CREATE (d1:Document {id: 'doc1', title: 'Sample Document'})
        CREATE (c1:Concept {name: 'Machine Learning', type: 'topic'})
        CREATE (c2:Concept {name: 'Neural Networks', type: 'subtopic'})
        CREATE (d1)-[:CONTAINS]->(c1)
        CREATE (c1)-[:RELATED_TO]->(c2)
    """)

async def seed_milvus_data(client):
    """Seed Milvus with sample vectors."""
    # Create collection
    await client.create_collection("documents", dimension=384)
    
    # Insert sample vectors
    vectors = [
        {"id": "doc1_chunk1", "vector": [0.1] * 384, "text": "Sample text chunk 1"},
        {"id": "doc1_chunk2", "vector": [0.2] * 384, "text": "Sample text chunk 2"},
    ]
    await client.insert_vectors(vectors)

async def main():
    config = LocalDatabaseConfig()
    factory = DatabaseClientFactory(config)
    
    postgres_client = factory.create_postgres_client()
    neo4j_client = factory.create_graph_store_client()
    milvus_client = factory.create_vector_store_client()
    
    await seed_postgres_data(postgres_client)
    await seed_neo4j_data(neo4j_client)
    await seed_milvus_data(milvus_client)
    
    print("Local data seeding completed!")

if __name__ == "__main__":
    asyncio.run(main())
```

## Performance Optimization

### Local Database Tuning

```yaml
# docker-compose.local.yml - Performance optimizations
services:
  postgres:
    environment:
      # Performance tuning for development
      - POSTGRES_SHARED_PRELOAD_LIBRARIES=pg_stat_statements
      - POSTGRES_MAX_CONNECTIONS=100
      - POSTGRES_SHARED_BUFFERS=256MB
      - POSTGRES_EFFECTIVE_CACHE_SIZE=1GB
    command: >
      postgres
      -c shared_preload_libraries=pg_stat_statements
      -c max_connections=100
      -c shared_buffers=256MB
      -c effective_cache_size=1GB
      -c maintenance_work_mem=64MB
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c default_statistics_target=100

  neo4j:
    environment:
      # Memory settings for development
      - NEO4J_dbms_memory_heap_initial__size=512m
      - NEO4J_dbms_memory_heap_max__size=1G
      - NEO4J_dbms_memory_pagecache_size=512m
      - NEO4J_dbms_tx__log_rotation_retention__policy=1G size

  milvus:
    environment:
      # Milvus performance tuning
      - MILVUS_QUERY_NODE_GRACEFUL_TIME=10
      - MILVUS_QUERY_NODE_STATS_TASK_DELAY_EXECUTE=10
```

## Monitoring and Observability

### Health Check Endpoints

```python
# src/multimodal_librarian/api/routers/health_local.py
from fastapi import APIRouter, Depends
from src.multimodal_librarian.clients.database_factory import DatabaseClientFactory

router = APIRouter()

@router.get("/health/databases")
async def check_database_health(
    factory: DatabaseClientFactory = Depends()
):
    """Check health of all local database services."""
    health_status = {
        "postgres": False,
        "neo4j": False,
        "milvus": False,
        "overall": False
    }
    
    try:
        # Check PostgreSQL
        postgres_client = factory.create_postgres_client()
        await postgres_client.execute("SELECT 1")
        health_status["postgres"] = True
    except Exception as e:
        health_status["postgres_error"] = str(e)
    
    try:
        # Check Neo4j
        neo4j_client = factory.create_graph_store_client()
        await neo4j_client.execute_query("RETURN 1")
        health_status["neo4j"] = True
    except Exception as e:
        health_status["neo4j_error"] = str(e)
    
    try:
        # Check Milvus
        milvus_client = factory.create_vector_store_client()
        await milvus_client.list_collections()
        health_status["milvus"] = True
    except Exception as e:
        health_status["milvus_error"] = str(e)
    
    health_status["overall"] = all([
        health_status["postgres"],
        health_status["neo4j"],
        health_status["milvus"]
    ])
    
    return health_status
```

## Migration and Deployment Strategy

### Phase 1: Database Client Abstraction
1. Create database client interfaces and factory
2. Implement local database clients
3. Update dependency injection to use factory
4. Test with existing AWS setup

### Phase 2: Docker Compose Setup
1. Create docker-compose.local.yml
2. Configure local database services
3. Add health checks and dependencies
4. Test service orchestration

### Phase 3: Configuration Management
1. Create local configuration classes
2. Update environment variable handling
3. Add configuration validation
4. Test environment switching

### Phase 4: Development Workflow
1. Update Makefile with local targets
2. Create data seeding scripts
3. Add monitoring and debugging tools
4. Update documentation

### Phase 5: Testing and Validation
1. Run full test suite against local services
2. Performance testing and optimization
3. Developer experience validation
4. Documentation and troubleshooting guides

This design provides a comprehensive approach to converting from AWS-native databases to local development alternatives while maintaining functionality and developer experience.