# Multi-stage Dockerfile for Multimodal Librarian
# Supports both local development and production deployment
# CRITICAL FIX: Platform specification to prevent "exec format error" on AWS Fargate

# =============================================================================
# BASE STAGE - Common dependencies and setup
# =============================================================================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TORCH_HOME=/app/.cache/torch \
    TRANSFORMERS_CACHE=/app/.cache/transformers \
    HF_HOME=/app/.cache/huggingface \
    DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies (full set for complete ML capabilities)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    wget \
    tesseract-ocr \
    tesseract-ocr-eng \
    libpq-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    espeak \
    espeak-data \
    libespeak1 \
    libespeak-dev \
    libasound2-dev \
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0 \
    libavcodec-extra \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy full requirements
COPY requirements.txt ./

# Install Python dependencies in stages to avoid dependency resolution issues
# Stage 1: Core dependencies first
RUN pip install --upgrade pip setuptools wheel

# Stage 2: Install core packages that others depend on
RUN pip install --timeout=1200 --retries=5 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org \
    numpy>=1.24.0 \
    packaging \
    typing-extensions>=4.8.0 \
    certifi \
    charset-normalizer \
    idna \
    urllib3 \
    requests==2.31.0 \
    six \
    python-dateutil==2.8.2 \
    pytz==2023.3 \
    "python-dotenv>=1.0.1,<2.0.0"

# Stage 3: Install PyTorch ecosystem with CPU-only version for faster download
RUN pip install --timeout=1200 --retries=5 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org \
    torch>=2.1.0,\<2.5.0+cpu \
    torchvision>=0.16.0,\<0.20.0+cpu \
    torchaudio>=2.1.0,\<2.5.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Stage 4: Install ML dependencies
RUN pip install --timeout=1200 --retries=5 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org \
    transformers>=4.35.0,\<4.50.0 \
    sentence-transformers>=2.2.0 \
    accelerate>=0.24.0,\<1.0.0 \
    datasets>=2.14.0,\<3.0.0 \
    evaluate>=0.4.0,\<1.0.0

# Stage 5: Install remaining dependencies
RUN pip install --timeout=1200 --retries=5 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt

# Download essential ML models and data
RUN python -c "import spacy; spacy.cli.download('en_core_web_sm')" && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" && \
    python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('averaged_perceptron_tagger')" && \
    python -c "import torch; print(f'PyTorch version: {torch.__version__}')" && \
    python -c "import transformers; print(f'Transformers version: {transformers.__version__}')" && \
    python -c "import cv2; print(f'OpenCV version: {cv2.__version__}')"

# Create necessary directories with proper permissions
RUN mkdir -p uploads media exports logs audit_logs \
    .cache/torch .cache/transformers .cache/huggingface \
    .cache/matplotlib \
    && chmod 755 uploads media exports logs audit_logs \
    && chmod 755 .cache/torch .cache/transformers .cache/huggingface \
    && chmod 755 .cache/matplotlib

# =============================================================================
# DEVELOPMENT STAGE - For local development with hot reload
# =============================================================================
FROM base as development

# Install development dependencies
RUN apt-get update && apt-get install -y \
    # Development tools
    vim \
    nano \
    htop \
    procps \
    net-tools \
    iputils-ping \
    telnet \
    # Debugging tools
    strace \
    gdb \
    # Additional utilities for development
    jq \
    tree \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy development requirements
COPY requirements-dev.txt ./

# Install development Python packages
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy project files (source code will be mounted as volume in docker-compose)
COPY src/ ./src/
COPY pyproject.toml ./

# Install the package in development mode
RUN pip install -e .

# Create non-root user for security but with sudo access for development
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/bash appuser \
    && apt-get update && apt-get install -y sudo \
    && echo "appuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && chown -R appuser:appuser /app \
    && rm -rf /var/lib/apt/lists/*

# Switch to non-root user
USER appuser

# Set up development environment
ENV PYTHONPATH=/app/src:/app \
    MPLCONFIGDIR=/app/.cache/matplotlib \
    ML_ENVIRONMENT=local \
    DATABASE_TYPE=local \
    DEBUG=true \
    LOG_LEVEL=DEBUG

# Expose ports for API, WebSocket, and debugging
EXPOSE 8000 5678

# Health check optimized for development (faster checks)
HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=2 \
    CMD curl -f http://localhost:8000/health/simple || exit 1

# Development command with enhanced hot reload
CMD ["python", "-m", "uvicorn", "multimodal_librarian.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src", "--reload-include", "*.py", "--reload-include", "*.yaml", "--reload-include", "*.yml", "--reload-include", "*.json", "--reload-exclude", "__pycache__", "--reload-exclude", "*.pyc", "--reload-exclude", "*.pyo", "--reload-exclude", "*.pyd", "--reload-exclude", ".git"]

# =============================================================================
# PRODUCTION STAGE - Optimized for production deployment
# =============================================================================
FROM base as production

# Copy project files
COPY src/ ./src/
COPY pyproject.toml ./

# Install the package
RUN pip install .

# Create non-root user for security (no sudo access in production)
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

# Production environment variables
ENV ML_ENVIRONMENT=aws \
    MPLCONFIGDIR=/app/.cache/matplotlib \
    DATABASE_TYPE=aws \
    DEBUG=false \
    LOG_LEVEL=INFO

# Expose ports for API and WebSocket
EXPOSE 8000

# Health check with longer startup time for ML model loading
# Using Python instead of curl (curl is not installed in this image)
HEALTHCHECK --interval=30s --timeout=15s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/simple', timeout=10).read()" || exit 1

# Run the production application (single worker for debugging startup issues)
CMD ["python", "-m", "uvicorn", "multimodal_librarian.main:app", "--host", "0.0.0.0", "--port", "8000"]