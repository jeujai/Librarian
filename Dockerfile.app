# Lightweight Dockerfile for Multimodal Librarian App Container
# ML models are loaded from the model-server container
# This keeps the app container lightweight for fast startup

FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install minimal system dependencies (no ML libraries)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    libpq-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy lightweight requirements (no ML models)
COPY requirements-app.txt ./

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install --timeout=600 --retries=3 -r requirements-app.txt

# Download NLTK data (lightweight)
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('averaged_perceptron_tagger')"

# Download spaCy sm model for NER-based relevance detection
RUN python -m spacy download en_core_web_sm

# Install scispaCy and biomedical NER model for Layer 2 scientific entity extraction
RUN pip install "scispacy>=0.5.0,<0.6.0" && \
    pip install https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz

# Create necessary directories
RUN mkdir -p uploads media exports logs audit_logs \
    .cache/matplotlib \
    && chmod 755 uploads media exports logs audit_logs \
    && chmod 755 .cache/matplotlib

# =============================================================================
# DEVELOPMENT STAGE
# =============================================================================
FROM base as development

# Install development tools
RUN apt-get update && apt-get install -y \
    vim nano htop procps net-tools iputils-ping jq tree \
    && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY src/ ./src/
COPY pyproject.toml ./

# Install in development mode
RUN pip install -e .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app/src:/app \
    MPLCONFIGDIR=/app/.cache/matplotlib \
    ML_ENVIRONMENT=local \
    DATABASE_TYPE=local \
    DEBUG=true \
    LOG_LEVEL=DEBUG \
    MODEL_SERVER_URL=http://model-server:8001 \
    MODEL_SERVER_ENABLED=true

EXPOSE 8000

# Fast health check - app starts quickly without ML models
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health/simple || exit 1

CMD ["python", "-m", "uvicorn", "multimodal_librarian.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src", "--ws-max-size", "157286400"]

# =============================================================================
# PRODUCTION STAGE
# =============================================================================
FROM base as production

COPY src/ ./src/
COPY pyproject.toml ./

RUN pip install .

RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV ML_ENVIRONMENT=aws \
    DATABASE_TYPE=aws \
    DEBUG=false \
    LOG_LEVEL=INFO \
    MODEL_SERVER_URL=http://model-server:8001 \
    MODEL_SERVER_ENABLED=true

EXPOSE 8000

# Fast health check - app starts quickly without ML models
HEALTHCHECK --interval=15s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/simple', timeout=5).read()" || exit 1

CMD ["python", "-m", "uvicorn", "multimodal_librarian.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-max-size", "157286400"]
