# Model Server Troubleshooting Guide

This guide helps diagnose and resolve common issues with the Model Server.

## Quick Diagnostics

### Check Model Server Status

```bash
# Check if model server is running
docker compose ps model-server

# Check model server health
curl http://localhost:8001/health

# Check model server logs
docker compose logs model-server --tail 50
```

### Check App-to-Model-Server Communication

```bash
# Test from inside the app container
docker compose exec app curl http://model-server:8001/health

# Check if MODEL_SERVER_URL is set correctly
docker compose exec app env | grep MODEL_SERVER
```

## Common Issues

### 1. Model Server Not Starting

**Symptoms:**
- Container exits immediately
- Health check fails
- "Model not loaded" errors

**Solutions:**

1. **Check memory allocation:**
   ```bash
   # Model server needs at least 2GB RAM
   docker stats model-server
   ```

2. **Check model download:**
   ```bash
   # Models are downloaded on first start
   docker compose logs model-server | grep -i "download\|loading"
   ```

3. **Verify dependencies:**
   ```bash
   docker compose exec model-server pip list | grep -E "sentence-transformers|spacy"
   ```

### 2. Embedding Generation Fails

**Symptoms:**
- 500 errors on `/embeddings` endpoint
- "Model not ready" responses
- Timeout errors

**Solutions:**

1. **Wait for model loading:**
   ```bash
   # Check if models are still loading
   curl http://localhost:8001/health | jq '.models'
   ```

2. **Check model status:**
   ```bash
   curl http://localhost:8001/health/ready
   ```

3. **Increase timeout:**
   ```bash
   # In .env or docker-compose.yml
   MODEL_SERVER_TIMEOUT=60.0
   ```

### 3. NLP Processing Fails

**Symptoms:**
- 500 errors on `/nlp/process` endpoint
- "spaCy model not found" errors

**Solutions:**

1. **Verify spaCy model is installed:**
   ```bash
   docker compose exec model-server python -c "import spacy; spacy.load('en_core_web_sm')"
   ```

2. **Download spaCy model:**
   ```bash
   docker compose exec model-server python -m spacy download en_core_web_sm
   ```

### 4. App Cannot Connect to Model Server

**Symptoms:**
- Connection refused errors
- Timeout errors
- "Model server unavailable" in logs

**Solutions:**

1. **Check network connectivity:**
   ```bash
   # Verify both containers are on same network
   docker network inspect librarian_default
   ```

2. **Check MODEL_SERVER_URL:**
   ```bash
   # Should be http://model-server:8001 in Docker
   docker compose exec app env | grep MODEL_SERVER_URL
   ```

3. **Check firewall/ports:**
   ```bash
   # Model server should be listening on 8001
   docker compose exec model-server netstat -tlnp | grep 8001
   ```

### 5. Slow Response Times

**Symptoms:**
- Requests take >5 seconds
- Timeouts on large batches

**Solutions:**

1. **Reduce batch size:**
   ```python
   # Instead of sending 100 texts at once
   embeddings = await client.generate_embeddings(texts[:20])
   ```

2. **Check CPU usage:**
   ```bash
   docker stats model-server
   ```

3. **Enable GPU (if available):**
   ```yaml
   # In docker-compose.yml
   model-server:
     deploy:
       resources:
         reservations:
           devices:
             - driver: nvidia
               count: 1
               capabilities: [gpu]
   ```

### 6. Memory Issues

**Symptoms:**
- Container killed (OOMKilled)
- "Out of memory" errors

**Solutions:**

1. **Increase memory limit:**
   ```yaml
   # In docker-compose.yml
   model-server:
     deploy:
       resources:
         limits:
           memory: 4G
   ```

2. **Use smaller models:**
   ```bash
   # In model server config
   EMBEDDING_MODEL=all-MiniLM-L6-v2  # Smaller model
   ```

## Graceful Degradation

When the model server is unavailable, the app should continue to function with reduced capabilities:

1. **Disable model server:**
   ```bash
   MODEL_SERVER_ENABLED=false
   ```

2. **Check fallback behavior:**
   ```bash
   curl http://localhost:8000/health/simple
   # Should return 200 even without model server
   ```

## Logs and Debugging

### Enable Debug Logging

```bash
# In model server
LOG_LEVEL=DEBUG docker compose up model-server

# In app
LOG_LEVEL=DEBUG docker compose up app
```

### View Detailed Logs

```bash
# Model server logs
docker compose logs model-server -f

# App logs related to model server
docker compose logs app | grep -i "model.server\|embedding\|nlp"
```

## Performance Tuning

### Optimize for Production

1. **Pre-download models in Dockerfile:**
   ```dockerfile
   RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```

2. **Use connection pooling:**
   ```python
   # Already configured in ModelServerClient
   client = ModelServerClient(max_connections=10)
   ```

3. **Enable caching:**
   ```bash
   # Mount model cache volume
   volumes:
     - model-cache:/root/.cache
   ```

## Getting Help

If you're still experiencing issues:

1. Check the [GitHub Issues](https://github.com/your-repo/issues)
2. Review the [DOCKER.md](../DOCKER.md) documentation
3. Check the model server source code in `src/model_server/`
