# Configuration Validation Guide

This document provides comprehensive guidance on validating your Multimodal Librarian configuration for local development.

## Overview

The configuration system includes multiple layers of validation to ensure your setup is correct and will work reliably:

1. **Schema Validation**: Ensures all values are the correct type and format
2. **Business Logic Validation**: Checks for conflicts and dependencies
3. **Connectivity Validation**: Tests actual connections to services
4. **Docker Environment Validation**: Verifies Docker setup
5. **Performance Validation**: Warns about potential performance issues

## Validation Methods

### 1. Automatic Validation

Configuration is automatically validated when you create a `LocalDatabaseConfig` instance:

```python
from multimodal_librarian.config.local_config import LocalDatabaseConfig

try:
    config = LocalDatabaseConfig()
    print("Configuration is valid!")
except ValueError as e:
    print(f"Configuration error: {e}")
```

### 2. Manual Validation

You can run validation manually to get detailed results:

```python
config = LocalDatabaseConfig()
validation = config.validate_configuration()

print(f"Valid: {validation['valid']}")
print(f"Backend: {validation['backend']}")

if validation['issues']:
    print("Issues found:")
    for issue in validation['issues']:
        print(f"  ❌ {issue}")

if validation['warnings']:
    print("Warnings:")
    for warning in validation['warnings']:
        print(f"  ⚠️  {warning}")
```

### 3. Connectivity Testing

Test actual connections to your services:

```python
connectivity = config.validate_connectivity(timeout=5)

print(f"Overall status: {connectivity['overall_status']}")

for service, result in connectivity['services'].items():
    status = "✅" if result['connected'] else "❌"
    response_time = f" ({result['response_time']}ms)" if result['response_time'] else ""
    print(f"{status} {service}: {result['host']}:{result['port']}{response_time}")
    
    if result.get('error'):
        print(f"    Error: {result['error']}")
```

### 4. Docker Environment Validation

Validate your Docker setup:

```python
docker_status = config.validate_docker_environment()

print(f"Docker available: {'✅' if docker_status['docker_available'] else '❌'}")
print(f"Compose available: {'✅' if docker_status['compose_available'] else '❌'}")
print(f"Compose file exists: {'✅' if docker_status['compose_file_exists'] else '❌'}")

if docker_status['errors']:
    print("Docker errors:")
    for error in docker_status['errors']:
        print(f"  ❌ {error}")
```

### 5. Comprehensive Validation with Fixes

Run validation and attempt automatic fixes:

```python
results = config.validate_and_fix_configuration()

print(f"Configuration valid: {results['validation']['valid']}")

if results['fixes_applied']:
    print("Fixes applied:")
    for fix in results['fixes_applied']:
        print(f"  ✅ {fix['action']}")

if results['fixes_failed']:
    print("Fixes failed:")
    for fix in results['fixes_failed']:
        print(f"  ❌ {fix['issue']}: {fix['error']}")

if results['recommendations']:
    print("Recommendations:")
    for rec in results['recommendations']:
        print(f"  💡 {rec}")
```

## Validation Categories

### Schema Validation

Validates data types, ranges, and formats:

```python
# These will raise ValueError during config creation
ML_POSTGRES_PORT=99999          # Port out of range (1-65535)
ML_CONNECTION_TIMEOUT=-1        # Negative timeout
ML_LOG_LEVEL=INVALID           # Invalid log level
ML_EMBEDDING_DIMENSION=0       # Zero dimension
```

**Common Schema Errors**:
- Port numbers outside 1-65535 range
- Negative timeout values
- Invalid log levels (must be DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Invalid Milvus metric types (must be L2, IP, COSINE, HAMMING, JACCARD)
- Invalid pool optimization strategies (must be conservative, balanced, aggressive, custom)

### Business Logic Validation

Checks for conflicts and dependencies:

```python
# Port conflicts
ML_POSTGRES_PORT=5432
ML_NEO4J_PORT=5432             # ❌ Port conflict

# Feature dependencies
ML_ENABLE_KNOWLEDGE_GRAPH=true
ML_ENABLE_GRAPH_DB=false       # ❌ Knowledge graph requires graph DB

# Resource constraints
ML_POSTGRES_POOL_SIZE=1000     # ⚠️  Very large pool size
```

**Common Business Logic Issues**:
- Port conflicts between services
- Feature dependencies not met
- Excessive resource allocation
- Weak or default passwords
- Debug mode enabled in production-like environments

### Connectivity Validation

Tests actual network connections:

```python
# Test individual service
result = config._test_tcp_connection('postgres', 5432, timeout=5)
print(f"Connected: {result['connected']}")
print(f"Response time: {result['response_time']}ms")

# Test all enabled services
connectivity = config.validate_connectivity()
```

**Connectivity Status Meanings**:
- `healthy`: All services reachable
- `partial`: Some services reachable
- `unhealthy`: No services reachable

### Docker Validation

Validates Docker environment:

```python
docker_status = config.validate_docker_environment()
```

**Docker Validation Checks**:
- Docker daemon available
- Docker Compose available (both `docker-compose` and `docker compose`)
- Compose file exists and is valid
- Services can be parsed from compose file

### Performance Validation

Warns about potential performance issues:

```python
# These generate warnings, not errors
ML_POSTGRES_POOL_SIZE=100      # ⚠️  Very large pool
ML_CONNECTION_TIMEOUT=600      # ⚠️  Very long timeout
ML_MAX_FILE_SIZE=2147483648    # ⚠️  Very large file size (2GB)
```

## Environment Detection Validation

The configuration factory can detect and validate your environment:

```python
from multimodal_librarian.config.config_factory import (
    detect_environment,
    get_configuration_factory
)

# Detect environment
env_info = detect_environment()
print(f"Detected: {env_info.detected_type}")
print(f"Confidence: {env_info.confidence:.2f}")

if env_info.confidence < 0.7:
    print("⚠️  Low confidence detection")

if env_info.warnings:
    print("Detection warnings:")
    for warning in env_info.warnings:
        print(f"  ⚠️  {warning}")

# Comprehensive environment validation
factory = get_configuration_factory()
validation = factory.validate_environment_setup("auto")

print(f"Overall status: {validation['overall_status']}")
if validation['recommendations']:
    print("Recommendations:")
    for rec in validation['recommendations']:
        print(f"  💡 {rec}")
```

## Command Line Validation

### Quick Validation Script

Create a validation script for command-line use:

```python
# scripts/validate-config.py
#!/usr/bin/env python3

import sys
from multimodal_librarian.config.local_config import LocalDatabaseConfig
from multimodal_librarian.config.config_factory import detect_environment

def main():
    print("🔍 Validating Multimodal Librarian Configuration...")
    
    # Environment detection
    print("\n📍 Environment Detection:")
    env_info = detect_environment()
    print(f"   Detected: {env_info.detected_type}")
    print(f"   Confidence: {env_info.confidence:.2f}")
    
    if env_info.warnings:
        for warning in env_info.warnings:
            print(f"   ⚠️  {warning}")
    
    # Configuration validation
    print("\n⚙️  Configuration Validation:")
    try:
        config = LocalDatabaseConfig()
        validation = config.validate_configuration()
        
        if validation['valid']:
            print("   ✅ Configuration is valid")
        else:
            print("   ❌ Configuration has issues:")
            for issue in validation['issues']:
                print(f"      - {issue}")
            return 1
        
        if validation['warnings']:
            print("   ⚠️  Warnings:")
            for warning in validation['warnings']:
                print(f"      - {warning}")
    
    except Exception as e:
        print(f"   ❌ Configuration error: {e}")
        return 1
    
    # Connectivity testing
    print("\n🔗 Connectivity Testing:")
    try:
        connectivity = config.validate_connectivity(timeout=3)
        
        if connectivity['overall_status'] == 'healthy':
            print("   ✅ All services reachable")
        elif connectivity['overall_status'] == 'partial':
            print("   ⚠️  Some services unreachable")
        else:
            print("   ❌ No services reachable")
        
        for service, result in connectivity['services'].items():
            status = "✅" if result['connected'] else "❌"
            print(f"      {status} {service}: {result['host']}:{result['port']}")
    
    except Exception as e:
        print(f"   ⚠️  Connectivity test failed: {e}")
    
    # Docker validation
    print("\n🐳 Docker Environment:")
    try:
        docker_status = config.validate_docker_environment()
        
        docker_ok = "✅" if docker_status['docker_available'] else "❌"
        compose_ok = "✅" if docker_status['compose_available'] else "❌"
        file_ok = "✅" if docker_status['compose_file_exists'] else "❌"
        
        print(f"   {docker_ok} Docker available")
        print(f"   {compose_ok} Docker Compose available")
        print(f"   {file_ok} Compose file exists")
        
        if docker_status['errors']:
            for error in docker_status['errors']:
                print(f"      ❌ {error}")
    
    except Exception as e:
        print(f"   ⚠️  Docker validation failed: {e}")
    
    print("\n✨ Validation complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### Usage

```bash
# Make script executable
chmod +x scripts/validate-config.py

# Run validation
python scripts/validate-config.py

# Or use make target
make validate-config
```

## Validation in CI/CD

### GitHub Actions Example

```yaml
# .github/workflows/validate-config.yml
name: Validate Configuration

on:
  pull_request:
    paths:
      - '.env.local.example'
      - 'src/multimodal_librarian/config/**'
      - 'docker-compose.local.yml'

jobs:
  validate:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Validate configuration
      run: |
        cp .env.local.example .env.local
        python scripts/validate-config.py
    
    - name: Validate Docker Compose
      run: |
        docker-compose -f docker-compose.local.yml config
```

## Common Validation Errors and Solutions

### Port Conflicts

**Error**: `Port 5432 is used by multiple services: PostgreSQL, API`

**Solution**:
```bash
# Change one of the conflicting ports
ML_API_PORT=8000
ML_POSTGRES_PORT=5432
```

### Feature Dependencies

**Error**: `Knowledge graph features require graph database to be enabled`

**Solution**:
```bash
# Enable the required dependency
ML_ENABLE_GRAPH_DB=true
ML_ENABLE_KNOWLEDGE_GRAPH=true

# Or disable the dependent feature
ML_ENABLE_KNOWLEDGE_GRAPH=false
```

### Weak Passwords

**Warning**: `PostgreSQL using weak or default password`

**Solution**:
```bash
# Use strong, unique passwords
ML_POSTGRES_PASSWORD=MyStr0ng!P@ssw0rd123
ML_NEO4J_PASSWORD=An0th3r!Str0ng#P@ss
```

### Service Unreachable

**Error**: `Cannot connect to postgres at postgres:5432`

**Solutions**:
```bash
# Check if services are running
docker-compose -f docker-compose.local.yml ps

# Start services if not running
docker-compose -f docker-compose.local.yml up -d

# Check service logs
docker-compose -f docker-compose.local.yml logs postgres

# For localhost development, use localhost instead of container names
ML_POSTGRES_HOST=localhost
ML_NEO4J_HOST=localhost
```

### Docker Issues

**Error**: `Docker is not available or not working`

**Solutions**:
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Start Docker daemon
sudo systemctl start docker

# Add user to docker group
sudo usermod -aG docker $USER
```

### Large Resource Allocation

**Warning**: `Total connection pool size (500) may consume excessive resources`

**Solution**:
```bash
# Reduce pool sizes for local development
ML_POSTGRES_POOL_SIZE=10
ML_POSTGRES_MAX_OVERFLOW=20
ML_NEO4J_POOL_SIZE=50
ML_REDIS_MAX_CONNECTIONS=10
```

## Best Practices

### 1. Validate Early and Often

```bash
# Validate after any configuration change
python scripts/validate-config.py

# Include validation in your development workflow
make validate-config
```

### 2. Use Test Configurations

```python
# Create test configurations for different scenarios
test_config = LocalDatabaseConfig.create_test_config(
    postgres_port=5433,
    enable_knowledge_graph=False
)
```

### 3. Monitor Configuration Health

```python
# Regularly check service health
connectivity = config.validate_connectivity()
if connectivity['overall_status'] != 'healthy':
    print("⚠️  Some services are down")
```

### 4. Document Custom Configurations

```bash
# Add comments to your .env.local file
# Custom port to avoid conflict with system PostgreSQL
ML_POSTGRES_PORT=5433

# Reduced pool size for development machine
ML_POSTGRES_POOL_SIZE=5
```

### 5. Version Control Validation

```bash
# Never commit .env.local, but do commit validation scripts
echo ".env.local" >> .gitignore
git add scripts/validate-config.py
```

This validation guide helps ensure your configuration is correct and your local development environment runs smoothly. For additional help, see the [Configuration Options](configuration-options.md) and [Troubleshooting Guide](../troubleshooting/configuration-troubleshooting.md).