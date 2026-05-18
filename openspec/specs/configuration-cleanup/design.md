# Configuration Cleanup Design

## Architecture Overview

### Current State Analysis
```
CURRENT MESS:
├── Dockerfiles (15+)
│   ├── Dockerfile.full-ml ✅ (working)
│   ├── Dockerfile.learning ❌ (experimental)
│   ├── Dockerfile.ai-enhanced ❌ (experimental)
│   └── ... (12+ more experimental)
├── Main Applications (8+)
│   ├── main_minimal.py ✅ (working)
│   ├── main_learning.py ❌ (experimental)
│   ├── main_ai_enhanced.py ❌ (experimental)
│   └── ... (5+ more experimental)
├── Deployment Scripts (20+)
│   ├── deploy-full-ml.sh ✅ (working)
│   ├── deploy-learning.sh ❌ (experimental)
│   └── ... (18+ more experimental)
└── Secrets
    ├── multimodal-librarian/full-ml/* ✅ (canonical)
    └── multimodal-librarian/learning/* ❌ (hack)
```

### Target State Architecture
```
CLEAN STRUCTURE:
├── Production Configuration
│   ├── Dockerfile ✅ (single, canonical)
│   ├── src/multimodal_librarian/main.py ✅ (single, canonical)
│   ├── scripts/deploy.sh ✅ (single, canonical)
│   ├── task-definition.json ✅ (single, canonical)
│   └── requirements.txt ✅ (consolidated)
├── Development Configuration
│   ├── Dockerfile.dev
│   ├── docker-compose.dev.yml
│   └── scripts/deploy-dev.sh
├── Archive (Reference Only)
│   ├── experimental/
│   │   ├── learning-configs/
│   │   ├── ai-enhanced-configs/
│   │   └── other-experiments/
│   └── README.md (explains what's archived)
└── Secrets (Canonical Only)
    └── multimodal-librarian/full-ml/*
```

## Detailed Design

### 1. File Consolidation Strategy

#### Production Files (Keep and Standardize)
```yaml
Current → Target:
  src/multimodal_librarian/main_minimal.py → src/multimodal_librarian/main.py
  Dockerfile.full-ml → Dockerfile
  scripts/deploy-full-ml.sh → scripts/deploy.sh
  full-ml-task-def.json → task-definition.json
  requirements-full-ml.txt → requirements.txt
```

#### Archive Strategy
```yaml
Archive Structure:
  archive/
    experimental/
      learning-deployment/
        - All learning-related configs
        - Dockerfile.learning
        - main_learning.py
        - deploy-learning.sh
      ai-enhanced-deployment/
        - All ai-enhanced configs
        - Dockerfile.ai-enhanced
        - main_ai_enhanced.py
      websocket-experiments/
        - WebSocket-related experiments
      cost-optimization/
        - Cost optimization experiments
    README.md: "What's archived and why"
```

#### Delete Strategy
```yaml
Delete Completely:
  - Duplicate/broken configurations
  - Patch scripts (patch-*.py, quick-fix-*.sh)
  - Temporary files (temp-*, patched-*)
  - Failed experiment artifacts
```

### 2. Secret Management Redesign

#### Current Secret Structure
```json
AWS Secrets Manager:
{
  "multimodal-librarian/full-ml/database": {
    "host": "actual-rds-endpoint",
    "port": 5432,
    "dbname": "multimodal_librarian",
    "username": "postgres",
    "password": "secure-password"
  },
  "multimodal-librarian/full-ml/redis": {
    "host": "actual-redis-endpoint",
    "port": 6379
  },
  "multimodal-librarian/full-ml/neo4j": {
    "host": "neo4j-endpoint",
    "port": 7687,
    "username": "neo4j",
    "password": "secure-password"
  },
  "multimodal-librarian/learning/database": "❌ HACK - DELETE",
  "multimodal-librarian/learning/redis": "❌ HACK - DELETE"
}
```

#### Target Secret Structure
```json
AWS Secrets Manager (Clean):
{
  "multimodal-librarian/full-ml/database": "✅ Keep",
  "multimodal-librarian/full-ml/redis": "✅ Keep", 
  "multimodal-librarian/full-ml/neo4j": "✅ Keep",
  "multimodal-librarian/full-ml/api-keys": "✅ Keep"
}
```

### 3. Application Code Consolidation

#### Main Application Design
```python
# src/multimodal_librarian/main.py (consolidated)
"""
Multimodal Librarian - Production Application

This is the canonical production application that consolidates
all working features from experimental versions.
"""

from fastapi import FastAPI
from .config import get_settings
from .database import get_database_connection
from .clients import Neo4jClient, RedisClient
from .api.routers import (
    chat,
    documents, 
    knowledge_graph,
    health
)

def create_app() -> FastAPI:
    """Create the canonical production application."""
    
    app = FastAPI(
        title="Multimodal Librarian",
        description="Production AI-powered document management system",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Feature flags (clean, consolidated)
    FEATURES = {
        "chat": True,
        "documents": True,
        "knowledge_graph": True,  # Will be enabled with Neo4j
        "analytics": True,
        "vector_search": True,
        "monitoring": True
    }
    
    # Include routers
    app.include_router(chat.router)
    app.include_router(documents.router)
    app.include_router(knowledge_graph.router)
    app.include_router(health.router)
    
    return app

app = create_app()
```

#### Configuration Management
```python
# src/multimodal_librarian/config.py (consolidated)
"""
Canonical configuration management.
All secrets use multimodal-librarian/full-ml/* naming.
"""

import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Application
    app_name: str = "Multimodal Librarian"
    debug: bool = False
    log_level: str = "INFO"
    
    # AWS
    aws_region: str = "us-east-1"
    secret_prefix: str = "multimodal-librarian/full-ml"
    
    # Database secrets (canonical naming)
    database_secret_name: str = "multimodal-librarian/full-ml/database"
    redis_secret_name: str = "multimodal-librarian/full-ml/redis"
    neo4j_secret_name: str = "multimodal-librarian/full-ml/neo4j"
    
    # Feature flags
    enable_neo4j: bool = True
    enable_analytics: bool = True
    enable_vector_search: bool = True
    
    class Config:
        env_file = ".env"

def get_settings() -> Settings:
    return Settings()
```

### 4. Deployment Consolidation

#### Canonical Deployment Script
```bash
#!/bin/bash
# scripts/deploy.sh - Canonical deployment script

set -e

CLUSTER_NAME="multimodal-librarian-full-ml"
SERVICE_NAME="multimodal-librarian-service"
TASK_DEFINITION="task-definition.json"

echo "🚀 Deploying Multimodal Librarian (Production)"

# Build and push Docker image
echo "📦 Building Docker image..."
docker build -t multimodal-librarian:latest .

# Tag and push to ECR
echo "📤 Pushing to ECR..."
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REPOSITORY
docker tag multimodal-librarian:latest $ECR_REPOSITORY:latest
docker push $ECR_REPOSITORY:latest

# Update ECS service
echo "🔄 Updating ECS service..."
aws ecs register-task-definition --cli-input-json file://$TASK_DEFINITION
aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --task-definition multimodal-librarian

# Wait for deployment
echo "⏳ Waiting for deployment to complete..."
aws ecs wait services-stable --cluster $CLUSTER_NAME --services $SERVICE_NAME

echo "✅ Deployment complete!"
```

#### Canonical Dockerfile
```dockerfile
# Dockerfile - Canonical production Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY pyproject.toml .

# Install application
RUN pip install -e .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "multimodal_librarian.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5. Documentation Structure

#### Deployment Documentation
```markdown
# docs/deployment/README.md

## Production Deployment

### Prerequisites
- AWS CLI configured
- Docker installed
- ECR repository created

### Deployment Process
1. Run `scripts/deploy.sh`
2. Monitor deployment: `scripts/monitor-deployment.sh`
3. Validate: `scripts/validate-deployment.sh`

### Rollback Process
1. Run `scripts/rollback.sh`
2. Specify previous task definition version

### Troubleshooting
- Check logs: `scripts/check-logs.sh`
- Health check: `curl https://your-domain/health`
```

#### Configuration Documentation
```markdown
# docs/configuration/README.md

## Configuration Management

### Secrets Structure
All secrets use the prefix: `multimodal-librarian/full-ml/`

### Environment Variables
- `LOG_LEVEL`: Application log level
- `DEBUG`: Enable debug mode
- `AWS_REGION`: AWS region for resources

### Feature Flags
- `enable_neo4j`: Enable knowledge graph features
- `enable_analytics`: Enable analytics dashboard
```

## Implementation Strategy

### Phase 1: Preparation and Analysis
1. **Create inventory of all files**
   - Catalog every Dockerfile, main file, script
   - Identify dependencies between files
   - Map current production usage

2. **Test current production state**
   - Verify current deployment is stable
   - Document all working endpoints
   - Create backup of current configuration

### Phase 2: File Consolidation
1. **Rename canonical files**
   - `main_minimal.py` → `main.py`
   - `Dockerfile.full-ml` → `Dockerfile`
   - `deploy-full-ml.sh` → `deploy.sh`

2. **Update all references**
   - Update import statements
   - Update deployment scripts
   - Update documentation

3. **Test consolidated configuration**
   - Build and test new Docker image
   - Deploy to test environment
   - Validate all functionality

### Phase 3: Archive and Cleanup
1. **Create archive structure**
   - Create `archive/experimental/` directory
   - Move experimental files to appropriate subdirectories
   - Create documentation for archived files

2. **Delete unnecessary files**
   - Remove broken/duplicate configurations
   - Remove temporary patch files
   - Remove failed experiments

### Phase 4: Secret Cleanup
1. **Verify canonical secret usage**
   - Ensure all code uses `full-ml/*` secrets
   - Test connectivity with canonical secrets
   - Update any remaining `learning/*` references

2. **Remove backward-compatible secrets**
   - Delete `multimodal-librarian/learning/*` secrets
   - Verify no services break
   - Update IAM policies if needed

### Phase 5: Documentation and Validation
1. **Create comprehensive documentation**
   - Deployment procedures
   - Configuration management
   - Troubleshooting guides

2. **Final validation**
   - Deploy clean configuration to production
   - Verify all functionality works
   - Monitor for any issues

## Risk Mitigation

### Backup Strategy
- Create full backup of current working state
- Tag current Docker images
- Export current task definitions
- Document current secret structure

### Rollback Plan
- Keep current task definition as rollback target
- Maintain current Docker images
- Keep current secrets until cleanup is validated
- Document rollback procedures

### Testing Strategy
- Test each phase in isolation
- Validate functionality after each change
- Use health checks to verify system state
- Monitor logs for any issues

## Success Metrics

### Quantitative Goals
- Reduce configuration files by 80%
- Single source of truth for each environment
- Zero backward-compatible hacks
- 100% consistent secret naming

### Qualitative Goals
- Clear, understandable codebase structure
- Predictable deployment process
- Maintainable configuration management
- Reduced cognitive load for developers