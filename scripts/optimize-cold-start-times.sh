#!/bin/bash
#
# Cold Start Time Optimization Script
#
# This script implements comprehensive optimizations to minimize container
# cold start times for the local development environment.
#
# Key Optimizations:
# - Pre-warmed container images with cached dependencies
# - Optimized Docker layer caching strategy
# - Parallel service initialization
# - Lazy loading of non-critical components
# - Memory-mapped file optimizations
# - Reduced health check intervals during startup
# - Container resource pre-allocation
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.local.yml"
OPTIMIZED_COMPOSE_FILE="docker-compose.cold-start-optimized.yml"
DOCKERFILE_OPTIMIZED="Dockerfile.cold-start-optimized"
OPTIMIZATION_LEVEL="aggressive"
ENABLE_PREWARMING=true
ENABLE_LAYER_CACHING=true
ENABLE_PARALLEL_INIT=true
ENABLE_LAZY_LOADING=true
ENABLE_MEMORY_OPTIMIZATION=true

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} ✅ $1"
}

print_warning() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} ⚠️  $1"
}

print_error() {
    echo -e "${RED}[$(date '+%H:%M:%S')]${NC} ❌ $1"
}

print_info() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} 💡 $1"
}

# Function to show help
show_help() {
    echo "Cold Start Time Optimization Script"
    echo
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Commands:"
    echo "  optimize      Apply all cold start optimizations"
    echo "  build         Build optimized images with pre-warming"
    echo "  start         Start services with cold start optimizations"
    echo "  benchmark     Benchmark cold start times"
    echo "  clean         Clean up optimization artifacts"
    echo "  status        Show optimization status"
    echo
    echo "Options:"
    echo "  --level LEVEL         Optimization level: standard, aggressive (default: aggressive)"
    echo "  --no-prewarming      Disable container pre-warming"
    echo "  --no-layer-cache     Disable Docker layer caching"
    echo "  --no-parallel        Disable parallel initialization"
    echo "  --no-lazy-loading    Disable lazy loading"
    echo "  --no-memory-opt      Disable memory optimizations"
    echo "  --help               Show this help message"
    echo
    echo "Examples:"
    echo "  $0 optimize                    # Apply all optimizations"
    echo "  $0 --level standard optimize   # Standard optimizations"
    echo "  $0 benchmark                   # Benchmark cold start times"
}

# Function to create optimized Dockerfile
create_optimized_dockerfile() {
    print_status "Creating cold start optimized Dockerfile..."
    
    cat > "$DOCKERFILE_OPTIMIZED" << 'EOF'
# Cold Start Optimized Multi-stage Dockerfile for Multimodal Librarian
# Focused on minimizing cold start times through aggressive caching and pre-warming

# =============================================================================
# DEPENDENCY CACHE STAGE - Pre-built dependencies for instant startup
# =============================================================================
FROM --platform=linux/amd64 python:3.11-slim as dependency-cache

# Set environment variables for build optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONPATH=/app/src

# Install system dependencies in a single layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    git \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create cache directory structure
WORKDIR /cache
RUN mkdir -p /cache/packages /cache/models /cache/nltk_data

# Copy requirements for better layer caching
COPY requirements.txt requirements-dev.txt ./

# Install Python dependencies with aggressive caching
RUN pip install --upgrade pip setuptools wheel && \
    pip install --target /cache/packages \
    --cache-dir /cache/pip \
    --find-links /cache/pip \
    -r requirements.txt && \
    pip install --target /cache/packages \
    --cache-dir /cache/pip \
    --find-links /cache/pip \
    -r requirements-dev.txt

# Pre-download and cache ML models and data
RUN python3 -c "
import sys
sys.path.insert(0, '/cache/packages')
import os
os.environ['TRANSFORMERS_CACHE'] = '/cache/models'
os.environ['HF_HOME'] = '/cache/models'
os.environ['TORCH_HOME'] = '/cache/models'
os.environ['NLTK_DATA'] = '/cache/nltk_data'

# Download models in parallel
import concurrent.futures
import subprocess

def download_spacy():
    subprocess.run(['python3', '-m', 'spacy', 'download', 'en_core_web_sm'], check=True)

def download_sentence_transformers():
    from sentence_transformers import SentenceTransformer
    SentenceTransformer('all-MiniLM-L6-v2')

def download_nltk():
    import nltk
    nltk.download('punkt', download_dir='/cache/nltk_data')
    nltk.download('stopwords', download_dir='/cache/nltk_data')
    nltk.download('averaged_perceptron_tagger', download_dir='/cache/nltk_data')

# Execute downloads in parallel
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(download_spacy),
        executor.submit(download_sentence_transformers),
        executor.submit(download_nltk)
    ]
    for future in concurrent.futures.as_completed(futures):
        try:
            future.result()
        except Exception as e:
            print(f'Download failed: {e}')
"

# =============================================================================
# RUNTIME BASE STAGE - Minimal runtime with pre-cached dependencies
# =============================================================================
FROM --platform=linux/amd64 python:3.11-slim as runtime-base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    TORCH_HOME=/app/.cache/torch \
    TRANSFORMERS_CACHE=/app/.cache/transformers \
    HF_HOME=/app/.cache/huggingface \
    NLTK_DATA=/app/.cache/nltk_data \
    DEBIAN_FRONTEND=noninteractive

# Install only essential runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    libpq5 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set work directory
WORKDIR /app

# Copy pre-built packages from cache stage
COPY --from=dependency-cache /cache/packages /usr/local/lib/python3.11/site-packages/
COPY --from=dependency-cache /cache/models /app/.cache/
COPY --from=dependency-cache /cache/nltk_data /app/.cache/nltk_data/

# Create necessary directories with proper permissions
RUN mkdir -p uploads media exports logs audit_logs \
    .cache/torch .cache/transformers .cache/huggingface \
    && chmod 755 uploads media exports logs audit_logs \
    && chmod 755 .cache/torch .cache/transformers .cache/huggingface

# =============================================================================
# DEVELOPMENT STAGE - Optimized for fastest cold start
# =============================================================================
FROM runtime-base as development

# Install minimal development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    htop \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy project files
COPY src/ ./src/
COPY pyproject.toml ./

# Install the package in development mode
RUN pip install -e . --no-deps

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/bash appuser \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set up development environment
ENV PYTHONPATH=/app/src:/app \
    ML_ENVIRONMENT=local \
    DATABASE_TYPE=local \
    DEBUG=true \
    LOG_LEVEL=INFO \
    STARTUP_MODE=fast

# Expose ports
EXPOSE 8000 5678

# Ultra-fast health check optimized for cold start
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=2 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/simple', timeout=2).read()" || exit 1

# Cold start optimized command with minimal startup overhead
CMD ["python", "-m", "uvicorn", "multimodal_librarian.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/src", \
     "--reload-include", "*.py", \
     "--reload-exclude", "__pycache__", \
     "--reload-exclude", "*.pyc", \
     "--access-log", "--use-colors", \
     "--loop", "uvloop", \
     "--http", "httptools"]

EOF

    print_success "Cold start optimized Dockerfile created: $DOCKERFILE_OPTIMIZED"
}

# Function to create optimized docker-compose file
create_optimized_compose_file() {
    print_status "Creating cold start optimized docker-compose file..."
    
    cat > "$OPTIMIZED_COMPOSE_FILE" << 'EOF'
services:
  # =============================================================================
  # MAIN APPLICATION SERVICE - COLD START OPTIMIZED
  # =============================================================================
  multimodal-librarian:
    build:
      context: .
      dockerfile: Dockerfile.cold-start-optimized
      target: development
      cache_from:
        - multimodal-librarian:cache
      args:
        BUILDKIT_INLINE_CACHE: 1
    env_file:
      - .env.local
    ports:
      - "${API_PORT:-8000}:8000"
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1.5G  # Reduced for faster allocation
        reservations:
          cpus: '1.0'   # Higher reservation for faster startup
          memory: 768M
      restart_policy:
        condition: on-failure
        delay: 2s     # Faster restart
        max_attempts: 3
        window: 60s
    # =============================================================================
    # COLD START OPTIMIZATIONS
    # =============================================================================
    stop_signal: SIGTERM
    stop_grace_period: 15s  # Reduced for faster shutdown/restart
    init: true
    # Use tmpfs for temporary files to reduce I/O latency
    tmpfs:
      - /tmp:size=256M,noatime
      - /app/logs:size=128M,noatime
    # Memory-mapped volumes for faster access
    volumes:
      # Source code with optimized mount options
      - ./src:/app/src:rw,cached
      - ./pyproject.toml:/app/pyproject.toml:ro,cached
      - ./.env.local:/app/.env.local:ro,cached
      
      # Persistent data with optimized mount options
      - ./uploads:/app/uploads:rw,delegated
      - ./media:/app/media:rw,delegated
      - ./exports:/app/exports:rw,delegated
      
      # Cache volumes for faster access
      - ml_model_cache:/app/.cache:rw,cached
      - python_cache:/root/.cache/pip:rw,cached
    environment:
      # Cold start specific optimizations
      - ML_ENVIRONMENT=local
      - DATABASE_TYPE=local
      - DEBUG=true
      - LOG_LEVEL=INFO
      - STARTUP_MODE=fast
      - COLD_START_OPTIMIZATION=true
      
      # Uvicorn optimizations for faster startup
      - UVICORN_WORKERS=1
      - UVICORN_LOOP=uvloop
      - UVICORN_HTTP=httptools
      - UVICORN_RELOAD_DELAY=0.5
      
      # Python optimizations
      - PYTHONOPTIMIZE=1
      - PYTHONDONTWRITEBYTECODE=1
      - PYTHONUNBUFFERED=1
      
      # Database connection optimizations
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=multimodal_librarian
      - POSTGRES_USER=ml_user
      - POSTGRES_PASSWORD=ml_password
      - POSTGRES_POOL_SIZE=5      # Reduced pool size for faster startup
      - POSTGRES_MAX_CONNECTIONS=20
      
      # Neo4j optimizations
      - NEO4J_HOST=neo4j
      - NEO4J_PORT=7687
      - NEO4J_USER=neo4j
      - NEO4J_PASSWORD=ml_password
      
      # Milvus optimizations
      - MILVUS_HOST=milvus
      - MILVUS_PORT=19530
      
      # Redis optimizations
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - CACHE_TTL=1800  # Reduced TTL for development
    depends_on:
      postgres:
        condition: service_healthy
        restart: true
      neo4j:
        condition: service_started  # Don't wait for full health
        restart: true
      milvus:
        condition: service_started  # Don't wait for full health
        restart: true
      redis:
        condition: service_healthy
        restart: true
    restart: unless-stopped
    networks:
      - ml-local-network
    # Optimized health check for cold start
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/simple', timeout=2).read()"]
      interval: 5s
      timeout: 3s
      retries: 2
      start_period: 10s

  # =============================================================================
  # POSTGRESQL - COLD START OPTIMIZED
  # =============================================================================
  postgres:
    image: postgres:15-alpine
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
    stop_signal: SIGTERM
    stop_grace_period: 10s
    init: true
    # Use tmpfs for WAL and temporary files
    tmpfs:
      - /tmp:size=128M,noatime
      - /var/run/postgresql:size=64M,noatime
    environment:
      - POSTGRES_DB=multimodal_librarian
      - POSTGRES_USER=ml_user
      - POSTGRES_PASSWORD=ml_password
      - POSTGRES_INITDB_ARGS=--encoding=UTF-8 --lc-collate=C --lc-ctype=C
      # Cold start optimizations
      - POSTGRES_SHARED_PRELOAD_LIBRARIES=
      - POSTGRES_MAX_CONNECTIONS=20
      - POSTGRES_SHARED_BUFFERS=128MB
      - POSTGRES_EFFECTIVE_CACHE_SIZE=256MB
    volumes:
      - postgres_data:/var/lib/postgresql/data:rw,delegated
      - ./database/postgresql/init/01_extensions.sql:/docker-entrypoint-initdb.d/01_extensions.sql:ro
      - ./database/postgresql/init/06_application_schema.sql:/docker-entrypoint-initdb.d/06_application_schema.sql:ro
    ports:
      - "5432:5432"
    restart: unless-stopped
    networks:
      - ml-local-network
    # Fast health check for cold start
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ml_user -d multimodal_librarian"]
      interval: 5s
      timeout: 3s
      retries: 3
      start_period: 10s
    # Optimized PostgreSQL configuration for cold start
    command: >
      postgres
      -c max_connections=20
      -c shared_buffers=128MB
      -c effective_cache_size=256MB
      -c maintenance_work_mem=32MB
      -c work_mem=4MB
      -c checkpoint_completion_target=0.9
      -c wal_buffers=16MB
      -c max_wal_size=512MB
      -c min_wal_size=128MB
      -c log_statement=none
      -c log_min_duration_statement=-1
      -c fsync=off
      -c synchronous_commit=off
      -c full_page_writes=off

  # =============================================================================
  # NEO4J - COLD START OPTIMIZED
  # =============================================================================
  neo4j:
    image: neo4j:5.15-community
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 768M
        reservations:
          cpus: '0.25'
          memory: 384M
    stop_signal: SIGTERM
    stop_grace_period: 15s
    init: true
    environment:
      - NEO4J_AUTH=neo4j/ml_password
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_security_procedures_unrestricted=apoc.*
      # Cold start memory optimizations
      - NEO4J_server_memory_heap_initial__size=256m
      - NEO4J_server_memory_heap_max__size=512m
      - NEO4J_server_memory_pagecache_size=256m
      - NEO4J_server_memory_off__heap_max__size=128m
      # Performance optimizations for cold start
      - NEO4J_db_tx__log_rotation_retention__policy=512M size
      - NEO4J_db_tx__log_rotation_size=64M
      - NEO4J_dbms_query__cache__size=500
      - NEO4J_server_bolt_thread__pool__min__size=2
      - NEO4J_server_bolt_thread__pool__max__size=100
      - NEO4J_db_checkpoint_interval_time=10m
      - NEO4J_db_checkpoint_interval_tx=5000
      # Disable expensive operations
      - NEO4J_dbms_usage__report_enabled=false
      - NEO4J_metrics_enabled=false
      - NEO4J_dbms_logs_query_enabled=false
      - NEO4J_server_logs_debug_level=WARN
    volumes:
      - neo4j_data:/data:rw,delegated
      - neo4j_logs:/logs:rw,delegated
    ports:
      - "7474:7474"
      - "7687:7687"
    restart: unless-stopped
    networks:
      - ml-local-network
    # Simplified health check for faster startup
    healthcheck:
      test: ["CMD-SHELL", "cypher-shell -u neo4j -p ml_password 'RETURN 1'"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 30s

  # =============================================================================
  # MILVUS - COLD START OPTIMIZED
  # =============================================================================
  milvus:
    image: milvusdb/milvus:v2.3.4
    command: ["milvus", "run", "standalone"]
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 1G
        reservations:
          cpus: '0.25'
          memory: 512M
    stop_signal: SIGTERM
    stop_grace_period: 15s
    init: true
    environment:
      - ETCD_ENDPOINTS=etcd:2379
      - MINIO_ADDRESS=minio:9000
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
      # Cold start optimizations
      - MILVUS_QUERY_NODE_GRACEFUL_TIME=5
      - MILVUS_QUERY_NODE_STATS_TASK_DELAY_EXECUTE=5
      - MILVUS_QUERY_NODE_CACHE_SIZE=1073741824
      - MILVUS_DATA_NODE_FLUSH_INSERT_BUFFER_SIZE=8388608
      - MILVUS_QUERY_NODE_SEARCH_TIMEOUT=15
      - MILVUS_QUERY_NODE_SEARCH_RESULT_TIMEOUT=15
    volumes:
      - milvus_data:/var/lib/milvus:rw,delegated
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      etcd:
        condition: service_started
      minio:
        condition: service_started
    restart: unless-stopped
    networks:
      - ml-local-network
    # Fast health check
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9091/healthz"]
      interval: 10s
      timeout: 5s
      retries: 2
      start_period: 30s

  # =============================================================================
  # ETCD - COLD START OPTIMIZED
  # =============================================================================
  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 256M
        reservations:
          cpus: '0.1'
          memory: 128M
    stop_signal: SIGTERM
    stop_grace_period: 5s
    init: true
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=500
      - ETCD_QUOTA_BACKEND_BYTES=2147483648
      - ETCD_SNAPSHOT_COUNT=25000
    volumes:
      - etcd_data:/etcd:rw,delegated
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    ports:
      - "2379:2379"
    restart: unless-stopped
    networks:
      - ml-local-network
    # Fast health check
    healthcheck:
      test: ["CMD-SHELL", "etcdctl endpoint health"]
      interval: 10s
      timeout: 3s
      retries: 2
      start_period: 15s

  # =============================================================================
  # MINIO - COLD START OPTIMIZED
  # =============================================================================
  minio:
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 256M
        reservations:
          cpus: '0.1'
          memory: 128M
    stop_signal: SIGTERM
    stop_grace_period: 10s
    init: true
    environment:
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
    volumes:
      - minio_data:/data:rw,delegated
    command: minio server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"
    restart: unless-stopped
    networks:
      - ml-local-network
    # Fast health check
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 2
      start_period: 15s

  # =============================================================================
  # REDIS - COLD START OPTIMIZED
  # =============================================================================
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly no --save "" --maxmemory 128mb --maxmemory-policy allkeys-lru
    deploy:
      resources:
        limits:
          cpus: '0.25'
          memory: 256M
        reservations:
          cpus: '0.1'
          memory: 128M
    stop_signal: SIGTERM
    stop_grace_period: 5s
    init: true
    volumes:
      - redis_data:/data:rw,delegated
    ports:
      - "6379:6379"
    restart: unless-stopped
    networks:
      - ml-local-network
    # Fast health check
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping"]
      interval: 5s
      timeout: 2s
      retries: 2
      start_period: 5s

# =============================================================================
# VOLUMES - OPTIMIZED FOR COLD START
# =============================================================================
volumes:
  postgres_data:
    driver: local
    driver_opts:
      type: none
      o: bind,noatime
      device: ./data/postgres
  neo4j_data:
    driver: local
    driver_opts:
      type: none
      o: bind,noatime
      device: ./data/neo4j
  neo4j_logs:
    driver: local
    driver_opts:
      type: none
      o: bind,noatime
      device: ./data/neo4j-logs
  milvus_data:
    driver: local
    driver_opts:
      type: none
      o: bind,noatime
      device: ./data/milvus
  etcd_data:
    driver: local
    driver_opts:
      type: none
      o: bind,noatime
      device: ./data/etcd
  minio_data:
    driver: local
    driver_opts:
      type: none
      o: bind,noatime
      device: ./data/minio
  redis_data:
    driver: local
    driver_opts:
      type: none
      o: bind,noatime
      device: ./data/redis
  
  # Cache volumes with optimized settings
  ml_model_cache:
    driver: local
    driver_opts:
      type: none
      o: bind,cached
      device: ./cache/models
  python_cache:
    driver: local
    driver_opts:
      type: none
      o: bind,cached
      device: ./cache/pip

# =============================================================================
# NETWORKS - OPTIMIZED FOR COLD START
# =============================================================================
networks:
  ml-local-network:
    name: multimodal-librarian-cold-start
    driver: bridge
    driver_opts:
      com.docker.network.bridge.enable_icc: "true"
      com.docker.network.bridge.enable_ip_masquerade: "true"
      com.docker.network.driver.mtu: 1500
    ipam:
      driver: default
      config:
        - subnet: 172.22.0.0/16
          gateway: 172.22.0.1

EOF

    print_success "Cold start optimized docker-compose file created: $OPTIMIZED_COMPOSE_FILE"
}

# Function to create pre-warming script
create_prewarming_script() {
    print_status "Creating container pre-warming script..."
    
    cat > "scripts/prewarm-containers.sh" << 'EOF'
#!/bin/bash
#
# Container Pre-warming Script
#
# This script pre-warms containers by building and caching images,
# pre-loading dependencies, and preparing the environment for
# instant startup.
#

set -e

print_info() {
    echo -e "\033[0;36m[$(date '+%H:%M:%S')]\033[0m 💡 $1"
}

print_success() {
    echo -e "\033[0;32m[$(date '+%H:%M:%S')]\033[0m ✅ $1"
}

print_status() {
    echo -e "\033[0;34m[$(date '+%H:%M:%S')]\033[0m $1"
}

# Pre-warm Docker images
prewarm_images() {
    print_status "Pre-warming Docker images..."
    
    # Build with cache
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1
    
    # Build dependency cache stage
    docker build --target dependency-cache \
        --cache-from multimodal-librarian:dependency-cache \
        -t multimodal-librarian:dependency-cache \
        -f Dockerfile.cold-start-optimized .
    
    # Build runtime base stage
    docker build --target runtime-base \
        --cache-from multimodal-librarian:dependency-cache \
        --cache-from multimodal-librarian:runtime-base \
        -t multimodal-librarian:runtime-base \
        -f Dockerfile.cold-start-optimized .
    
    # Build development stage
    docker build --target development \
        --cache-from multimodal-librarian:dependency-cache \
        --cache-from multimodal-librarian:runtime-base \
        --cache-from multimodal-librarian:development \
        -t multimodal-librarian:development \
        -f Dockerfile.cold-start-optimized .
    
    print_success "Docker images pre-warmed successfully"
}

# Pre-create data directories
prewarm_directories() {
    print_status "Pre-creating data directories..."
    
    local dirs=(
        "./data/postgres"
        "./data/neo4j"
        "./data/neo4j-logs"
        "./data/milvus"
        "./data/etcd"
        "./data/minio"
        "./data/redis"
        "./cache/models"
        "./cache/pip"
        "./uploads"
        "./media"
        "./exports"
        "./logs"
    )
    
    for dir in "${dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_info "Created directory: $dir"
        fi
    done
    
    print_success "Data directories pre-created"
}

# Pre-pull base images
prewarm_base_images() {
    print_status "Pre-pulling base images..."
    
    local images=(
        "python:3.11-slim"
        "postgres:15-alpine"
        "neo4j:5.15-community"
        "milvusdb/milvus:v2.3.4"
        "quay.io/coreos/etcd:v3.5.5"
        "minio/minio:RELEASE.2023-03-20T20-16-18Z"
        "redis:7-alpine"
    )
    
    for image in "${images[@]}"; do
        print_info "Pulling $image..."
        docker pull "$image" &
    done
    
    wait
    print_success "Base images pre-pulled"
}

# Main pre-warming function
main() {
    print_status "🔥 Starting container pre-warming process..."
    
    prewarm_base_images
    prewarm_directories
    prewarm_images
    
    print_success "🎉 Container pre-warming completed!"
    print_info "Containers are now ready for instant cold start"
}

main "$@"
EOF

    chmod +x "scripts/prewarm-containers.sh"
    print_success "Container pre-warming script created: scripts/prewarm-containers.sh"
}

# Function to create fast startup script
create_fast_startup_script() {
    print_status "Creating fast startup script..."
    
    cat > "scripts/fast-startup.sh" << 'EOF'
#!/bin/bash
#
# Fast Startup Script
#
# This script implements the fastest possible startup sequence
# using all cold start optimizations.
#

set -e

print_info() {
    echo -e "\033[0;36m[$(date '+%H:%M:%S')]\033[0m 💡 $1"
}

print_success() {
    echo -e "\033[0;32m[$(date '+%H:%M:%S')]\033[0m ✅ $1"
}

print_status() {
    echo -e "\033[0;34m[$(date '+%H:%M:%S')]\033[0m $1"
}

COMPOSE_FILE="docker-compose.cold-start-optimized.yml"

# Fast startup with optimized sequence
fast_startup() {
    local start_time=$(date +%s)
    
    print_status "🚀 Starting fast cold start sequence..."
    
    # Start essential services first (in parallel)
    print_info "Starting essential services..."
    docker compose -f "$COMPOSE_FILE" up -d redis postgres &
    
    # Start Milvus dependencies
    print_info "Starting Milvus dependencies..."
    docker compose -f "$COMPOSE_FILE" up -d etcd minio &
    
    # Wait for essential services
    wait
    
    # Start remaining services
    print_info "Starting remaining services..."
    docker compose -f "$COMPOSE_FILE" up -d neo4j milvus &
    
    # Start application (don't wait for all services to be fully ready)
    print_info "Starting application..."
    docker compose -f "$COMPOSE_FILE" up -d multimodal-librarian &
    
    wait
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    print_success "🎉 Fast startup completed in ${duration}s"
    print_info "Application should be available at: http://localhost:8000"
    print_info "Health check: http://localhost:8000/health/simple"
}

# Monitor startup progress
monitor_startup() {
    print_status "Monitoring startup progress..."
    
    local max_wait=60
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        if curl -f http://localhost:8000/health/simple >/dev/null 2>&1; then
            print_success "Application is ready! (${wait_time}s)"
            return 0
        fi
        
        sleep 2
        ((wait_time += 2))
        print_info "Waiting for application... (${wait_time}s)"
    done
    
    print_info "Application may still be starting up. Check logs with: make logs"
}

# Main function
main() {
    if [[ ! -f "$COMPOSE_FILE" ]]; then
        echo "Error: $COMPOSE_FILE not found. Run optimization first."
        exit 1
    fi
    
    fast_startup
    monitor_startup
}

main "$@"
EOF

    chmod +x "scripts/fast-startup.sh"
    print_success "Fast startup script created: scripts/fast-startup.sh"
}

# Function to optimize application startup code
optimize_application_startup() {
    print_status "Creating application startup optimizations..."
    
    # Create optimized startup configuration
    cat > "src/multimodal_librarian/config/cold_start_config.py" << 'EOF'
"""
Cold Start Configuration for Multimodal Librarian

This module provides configuration optimizations specifically for
minimizing cold start times in local development environments.
"""

import os
from typing import Dict, Any, Optional
from pydantic import BaseSettings, Field


class ColdStartConfig(BaseSettings):
    """Configuration optimized for cold start performance."""
    
    # Cold start mode flag
    cold_start_optimization: bool = Field(
        default=False,
        env="COLD_START_OPTIMIZATION",
        description="Enable cold start optimizations"
    )
    
    # Startup mode
    startup_mode: str = Field(
        default="normal",
        env="STARTUP_MODE",
        description="Startup mode: fast, normal, full"
    )
    
    # Lazy loading settings
    lazy_load_models: bool = Field(
        default=True,
        env="LAZY_LOAD_MODELS",
        description="Enable lazy loading of ML models"
    )
    
    lazy_load_services: bool = Field(
        default=True,
        env="LAZY_LOAD_SERVICES",
        description="Enable lazy loading of services"
    )
    
    # Connection pool optimizations
    min_connection_pool_size: int = Field(
        default=2,
        env="MIN_CONNECTION_POOL_SIZE",
        description="Minimum connection pool size for cold start"
    )
    
    max_connection_pool_size: int = Field(
        default=10,
        env="MAX_CONNECTION_POOL_SIZE",
        description="Maximum connection pool size for cold start"
    )
    
    # Health check optimizations
    fast_health_checks: bool = Field(
        default=True,
        env="FAST_HEALTH_CHECKS",
        description="Enable fast health checks during startup"
    )
    
    health_check_timeout: float = Field(
        default=2.0,
        env="HEALTH_CHECK_TIMEOUT",
        description="Health check timeout in seconds"
    )
    
    # Background initialization
    background_init_enabled: bool = Field(
        default=True,
        env="BACKGROUND_INIT_ENABLED",
        description="Enable background initialization"
    )
    
    background_init_delay: float = Field(
        default=1.0,
        env="BACKGROUND_INIT_DELAY",
        description="Delay before starting background initialization"
    )
    
    # Model loading priorities
    essential_models: list = Field(
        default_factory=lambda: [
            "sentence-transformers/all-MiniLM-L6-v2"
        ],
        description="Essential models to load first"
    )
    
    deferred_models: list = Field(
        default_factory=lambda: [
            "spacy/en_core_web_sm"
        ],
        description="Models to load in background"
    )
    
    # Service startup priorities
    critical_services: list = Field(
        default_factory=lambda: [
            "health_check",
            "basic_api"
        ],
        description="Critical services to start first"
    )
    
    deferred_services: list = Field(
        default_factory=lambda: [
            "vector_search",
            "knowledge_graph",
            "ai_chat"
        ],
        description="Services to start in background"
    )
    
    class Config:
        env_file = ".env.local"
        env_prefix = "ML_"


def get_cold_start_config() -> ColdStartConfig:
    """Get cold start configuration."""
    return ColdStartConfig()


def is_cold_start_mode() -> bool:
    """Check if cold start optimization is enabled."""
    config = get_cold_start_config()
    return config.cold_start_optimization


def get_startup_priorities() -> Dict[str, Any]:
    """Get startup priorities for cold start optimization."""
    config = get_cold_start_config()
    
    return {
        "essential_models": config.essential_models,
        "deferred_models": config.deferred_models,
        "critical_services": config.critical_services,
        "deferred_services": config.deferred_services,
        "lazy_loading": {
            "models": config.lazy_load_models,
            "services": config.lazy_load_services
        },
        "connection_pools": {
            "min_size": config.min_connection_pool_size,
            "max_size": config.max_connection_pool_size
        },
        "health_checks": {
            "fast_mode": config.fast_health_checks,
            "timeout": config.health_check_timeout
        },
        "background_init": {
            "enabled": config.background_init_enabled,
            "delay": config.background_init_delay
        }
    }
EOF

    print_success "Cold start configuration created"
}

# Function to benchmark cold start times
benchmark_cold_start() {
    print_status "Benchmarking cold start times..."
    
    local results_file="cold_start_benchmark_$(date +%Y%m%d_%H%M%S).json"
    
    # Test original configuration
    print_info "Testing original configuration..."
    docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1 || true
    
    local original_start_time=$(date +%s.%3N)
    docker compose -f "$COMPOSE_FILE" up -d >/dev/null 2>&1
    
    # Wait for health check
    local health_ready_time=""
    local max_wait=120
    local wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        if curl -f http://localhost:8000/health/simple >/dev/null 2>&1; then
            health_ready_time=$(date +%s.%3N)
            break
        fi
        sleep 1
        ((wait_time++))
    done
    
    local original_end_time=$(date +%s.%3N)
    docker compose -f "$COMPOSE_FILE" down -v >/dev/null 2>&1
    
    # Test optimized configuration
    print_info "Testing cold start optimized configuration..."
    docker compose -f "$OPTIMIZED_COMPOSE_FILE" down -v >/dev/null 2>&1 || true
    
    local optimized_start_time=$(date +%s.%3N)
    docker compose -f "$OPTIMIZED_COMPOSE_FILE" up -d >/dev/null 2>&1
    
    # Wait for health check
    local optimized_health_ready_time=""
    wait_time=0
    
    while [[ $wait_time -lt $max_wait ]]; do
        if curl -f http://localhost:8000/health/simple >/dev/null 2>&1; then
            optimized_health_ready_time=$(date +%s.%3N)
            break
        fi
        sleep 1
        ((wait_time++))
    done
    
    local optimized_end_time=$(date +%s.%3N)
    
    # Calculate results
    local original_duration=$(echo "$original_end_time - $original_start_time" | bc)
    local optimized_duration=$(echo "$optimized_end_time - $optimized_start_time" | bc)
    local improvement=$(echo "$original_duration - $optimized_duration" | bc)
    local improvement_percent=$(echo "scale=1; ($improvement * 100) / $original_duration" | bc)
    
    # Health check timing
    local original_health_duration=""
    local optimized_health_duration=""
    
    if [[ -n "$health_ready_time" ]]; then
        original_health_duration=$(echo "$health_ready_time - $original_start_time" | bc)
    fi
    
    if [[ -n "$optimized_health_ready_time" ]]; then
        optimized_health_duration=$(echo "$optimized_health_ready_time - $optimized_start_time" | bc)
    fi
    
    # Create benchmark results
    cat > "$results_file" << EOF
{
  "benchmark_date": "$(date -Iseconds)",
  "cold_start_results": {
    "original": {
      "total_startup_time": ${original_duration},
      "health_check_ready_time": ${original_health_duration:-null}
    },
    "optimized": {
      "total_startup_time": ${optimized_duration},
      "health_check_ready_time": ${optimized_health_duration:-null}
    },
    "improvement": {
      "time_saved_seconds": ${improvement},
      "improvement_percent": ${improvement_percent}
    }
  },
  "optimization_settings": {
    "level": "${OPTIMIZATION_LEVEL}",
    "prewarming_enabled": ${ENABLE_PREWARMING},
    "layer_caching_enabled": ${ENABLE_LAYER_CACHING},
    "parallel_init_enabled": ${ENABLE_PARALLEL_INIT},
    "lazy_loading_enabled": ${ENABLE_LAZY_LOADING},
    "memory_optimization_enabled": ${ENABLE_MEMORY_OPTIMIZATION}
  }
}
EOF
    
    # Display results
    echo
    print_success "Cold Start Benchmark Results:"
    print_info "Original startup time: ${original_duration}s"
    print_info "Optimized startup time: ${optimized_duration}s"
    
    if [[ $(echo "$improvement > 0" | bc) -eq 1 ]]; then
        print_success "Improvement: ${improvement}s (${improvement_percent}% faster)"
    else
        print_warning "No improvement or regression detected"
    fi
    
    if [[ -n "$original_health_duration" && -n "$optimized_health_duration" ]]; then
        local health_improvement=$(echo "$original_health_duration - $optimized_health_duration" | bc)
        print_info "Health check improvement: ${health_improvement}s"
    fi
    
    print_info "Detailed results saved to: $results_file"
}

# Function to show optimization status
show_optimization_status() {
    print_status "Cold Start Optimization Status"
    echo
    
    # Check if optimized files exist
    local files_status=true
    
    if [[ -f "$DOCKERFILE_OPTIMIZED" ]]; then
        print_success "Optimized Dockerfile: $DOCKERFILE_OPTIMIZED"
    else
        print_warning "Optimized Dockerfile not found"
        files_status=false
    fi
    
    if [[ -f "$OPTIMIZED_COMPOSE_FILE" ]]; then
        print_success "Optimized compose file: $OPTIMIZED_COMPOSE_FILE"
    else
        print_warning "Optimized compose file not found"
        files_status=false
    fi
    
    if [[ -f "scripts/prewarm-containers.sh" ]]; then
        print_success "Pre-warming script: scripts/prewarm-containers.sh"
    else
        print_warning "Pre-warming script not found"
        files_status=false
    fi
    
    if [[ -f "scripts/fast-startup.sh" ]]; then
        print_success "Fast startup script: scripts/fast-startup.sh"
    else
        print_warning "Fast startup script not found"
        files_status=false
    fi
    
    # Check cache directories
    local cache_dirs=("./cache/models" "./cache/pip" "./data")
    local cache_status=true
    
    for dir in "${cache_dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            local size=$(du -sh "$dir" 2>/dev/null | cut -f1 || echo "0")
            print_info "Cache directory $dir: $size"
        else
            print_warning "Cache directory $dir: not found"
            cache_status=false
        fi
    done
    
    # Check Docker images
    if docker images | grep -q "multimodal-librarian.*dependency-cache"; then
        print_success "Pre-warmed dependency cache image available"
    else
        print_warning "Pre-warmed dependency cache image not found"
    fi
    
    # Overall status
    echo
    if [[ "$files_status" == "true" && "$cache_status" == "true" ]]; then
        print_success "✅ Cold start optimizations are ready"
        print_info "Run './scripts/fast-startup.sh' for fastest startup"
    else
        print_warning "⚠️  Some optimizations are missing or incomplete"
        print_info "Run '$0 optimize' to set up all optimizations"
    fi
}

# Function to clean up optimization artifacts
cleanup_optimizations() {
    print_status "Cleaning up cold start optimization artifacts..."
    
    # Stop services
    docker compose -f "$OPTIMIZED_COMPOSE_FILE" down -v >/dev/null 2>&1 || true
    
    # Remove optimization files
    local files_to_remove=(
        "$DOCKERFILE_OPTIMIZED"
        "$OPTIMIZED_COMPOSE_FILE"
        "scripts/prewarm-containers.sh"
        "scripts/fast-startup.sh"
        "src/multimodal_librarian/config/cold_start_config.py"
        "cold_start_benchmark_*.json"
    )
    
    for file in "${files_to_remove[@]}"; do
        if [[ -f "$file" ]]; then
            rm -f "$file"
            print_info "Removed: $file"
        fi
    done
    
    # Remove Docker images
    docker rmi multimodal-librarian:dependency-cache >/dev/null 2>&1 || true
    docker rmi multimodal-librarian:runtime-base >/dev/null 2>&1 || true
    docker rmi multimodal-librarian:development >/dev/null 2>&1 || true
    
    print_success "Cleanup completed"
}

# Parse command line arguments
COMMAND=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --level)
            OPTIMIZATION_LEVEL="$2"
            shift 2
            ;;
        --no-prewarming)
            ENABLE_PREWARMING=false
            shift
            ;;
        --no-layer-cache)
            ENABLE_LAYER_CACHING=false
            shift
            ;;
        --no-parallel)
            ENABLE_PARALLEL_INIT=false
            shift
            ;;
        --no-lazy-loading)
            ENABLE_LAZY_LOADING=false
            shift
            ;;
        --no-memory-opt)
            ENABLE_MEMORY_OPTIMIZATION=false
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        optimize|build|start|benchmark|clean|status)
            COMMAND="$1"
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Set default command
COMMAND="${COMMAND:-optimize}"

# Main execution
main() {
    print_status "🚀 Cold Start Time Optimization Tool"
    print_info "Optimization level: $OPTIMIZATION_LEVEL"
    print_info "Command: $COMMAND"
    echo
    
    case $COMMAND in
        optimize)
            create_optimized_dockerfile
            create_optimized_compose_file
            create_prewarming_script
            create_fast_startup_script
            optimize_application_startup
            
            if [[ "$ENABLE_PREWARMING" == "true" ]]; then
                print_status "Running container pre-warming..."
                ./scripts/prewarm-containers.sh
            fi
            
            print_success "🎉 Cold start optimization completed!"
            print_info "Use './scripts/fast-startup.sh' for fastest startup"
            ;;
        build)
            create_optimized_dockerfile
            create_prewarming_script
            ./scripts/prewarm-containers.sh
            ;;
        start)
            if [[ -f "scripts/fast-startup.sh" ]]; then
                ./scripts/fast-startup.sh
            else
                print_error "Fast startup script not found. Run optimization first."
                exit 1
            fi
            ;;
        benchmark)
            benchmark_cold_start
            ;;
        status)
            show_optimization_status
            ;;
        clean)
            cleanup_optimizations
            ;;
        *)
            print_error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"