# Sample Data Generation Scripts

This directory contains scripts to generate realistic sample data for local development of the Multimodal Librarian application.

## Overview

The sample data generation scripts create:

- **Users and Authentication Data**: Sample user accounts with proper password hashing, roles, and API keys
- **Documents and Metadata**: Sample PDF documents with processing status, chunks, and metadata
- **Conversations and Chat History**: Sample conversation threads with realistic message exchanges
- **Analytics and Metrics Data**: Sample usage analytics, audit logs, and system metrics

## Quick Start

### Generate All Sample Data

The easiest way to populate your local development database:

```bash
# Generate all sample data (recommended)
python scripts/seed-all-sample-data.py

# Quick setup with smaller datasets
python scripts/seed-all-sample-data.py --quick

# Reset existing data and generate fresh data
python scripts/seed-all-sample-data.py --reset

# Verbose output for debugging
python scripts/seed-all-sample-data.py --verbose
```

### Individual Scripts

You can also run individual scripts for specific data types:

```bash
# Generate sample users
python scripts/seed-sample-users.py --count 10

# Generate sample documents with chunks
python scripts/seed-sample-documents.py --count 20 --with-chunks

# Generate sample conversations
python scripts/seed-sample-conversations.py --count 15

# Generate analytics data for 30 days
python scripts/seed-sample-analytics.py --days 30
```

## Prerequisites

### 1. Database Services Running

Ensure your local database services are running:

```bash
# Start local development environment
make dev-local

# Or start just the databases
docker-compose -f docker-compose.local.yml up -d postgres neo4j milvus
```

### 2. Database Schema Initialized

The database tables should be created before running the scripts:

```bash
# Run database migrations
python -m src.multimodal_librarian.database.migrations
```

### 3. Python Dependencies

Install required dependencies:

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Or install the package in development mode
pip install -e .
```

## Script Details

### 1. User Generation (`seed-sample-users.py`)

Creates sample user accounts with authentication data.

**Features:**
- Predefined users (admin, researcher, regular users)
- Proper password hashing with salt
- Role-based permissions (admin, ml_researcher, user, read_only)
- API keys for programmatic access
- Realistic user metadata

**Usage:**
```bash
python scripts/seed-sample-users.py [OPTIONS]

Options:
  --count N        Number of users to create (default: 10)
  --reset          Drop existing users before creating new ones
  --verbose        Enable verbose logging
```

**Sample Users Created:**
- `admin` / `admin123` (Administrator)
- `researcher` / `research123` (ML Researcher)
- `alice_dev` / `alice123` (Regular User)
- `bob_tester` / `bob123` (Regular User)
- `charlie_readonly` / `charlie123` (Read-only User)

### 2. Document Generation (`seed-sample-documents.py`)

Creates sample documents with realistic metadata and processing status.

**Features:**
- Technical documents (ML, AI, Computer Science topics)
- Realistic file sizes, page counts, and processing times
- Multiple processing statuses (completed, processing, failed)
- Document chunks for completed documents
- Knowledge source entries for search integration

**Usage:**
```bash
python scripts/seed-sample-documents.py [OPTIONS]

Options:
  --count N        Number of documents to create (default: 20)
  --reset          Drop existing documents before creating new ones
  --with-chunks    Generate sample chunks for documents
  --verbose        Enable verbose logging
```

**Document Types:**
- Machine Learning Fundamentals
- Deep Learning with PyTorch
- Natural Language Processing Handbook
- Computer Vision Applications
- Data Science Ethics
- And more technical documents...

### 3. Conversation Generation (`seed-sample-conversations.py`)

Creates sample conversation threads with realistic chat history.

**Features:**
- Technical AI/ML discussion topics
- Alternating user/system message patterns
- Knowledge references in system responses
- Realistic timestamps and conversation flow
- Chat message records for quick access

**Usage:**
```bash
python scripts/seed-sample-conversations.py [OPTIONS]

Options:
  --count N                    Number of conversations (default: 15)
  --reset                      Drop existing conversations first
  --messages-per-conversation M Average messages per conversation (default: 8)
  --verbose                    Enable verbose logging
```

**Conversation Topics:**
- Machine Learning Basics
- Neural Networks Deep Dive
- Data Preprocessing Techniques
- Computer Vision Applications
- Natural Language Processing
- And more technical discussions...

### 4. Analytics Generation (`seed-sample-analytics.py`)

Creates sample analytics data and system metrics.

**Features:**
- Realistic usage patterns over time
- Multiple event types (uploads, searches, logins, errors)
- Security incidents and audit logs
- User interaction feedback
- Performance metrics and system events

**Usage:**
```bash
python scripts/seed-sample-analytics.py [OPTIONS]

Options:
  --days N           Number of days of historical data (default: 30)
  --reset            Drop existing analytics data first
  --events-per-day M Average events per day (default: 100)
  --verbose          Enable verbose logging
```

**Analytics Data Types:**
- Document uploads and processing
- Chat messages and searches
- User authentication events
- System errors and warnings
- Security incidents
- User interaction feedback

## Configuration

### Environment Variables

The scripts use the same configuration as the main application. Key environment variables:

```bash
# Database configuration
ML_POSTGRES_HOST=localhost
ML_POSTGRES_PORT=5432
ML_POSTGRES_DB=multimodal_librarian
ML_POSTGRES_USER=ml_user
ML_POSTGRES_PASSWORD=ml_password

# Neo4j configuration
ML_NEO4J_HOST=localhost
ML_NEO4J_PORT=7687
ML_NEO4J_USER=neo4j
ML_NEO4J_PASSWORD=ml_password

# Milvus configuration
ML_MILVUS_HOST=localhost
ML_MILVUS_PORT=19530
```

### Configuration Files

The scripts automatically load configuration from:
1. `.env.local` file (if exists)
2. Environment variables with `ML_` prefix
3. Default values for local development

## Data Relationships

The generated data maintains proper relationships:

```
Users
├── Documents (owned by users)
│   ├── Document Chunks (for completed documents)
│   └── Knowledge Sources (for search integration)
├── Conversations (user chat history)
│   ├── Messages (conversation content)
│   └── Chat Messages (quick access records)
└── Analytics Data
    ├── Audit Logs (user actions)
    ├── Interaction Feedback (user behavior)
    └── Security Incidents (system events)
```

## Troubleshooting

### Common Issues

1. **Database Connection Errors**
   ```bash
   # Check if services are running
   docker-compose -f docker-compose.local.yml ps
   
   # Restart services if needed
   docker-compose -f docker-compose.local.yml restart
   ```

2. **Permission Errors**
   ```bash
   # Make scripts executable
   chmod +x scripts/*.py
   ```

3. **Import Errors**
   ```bash
   # Ensure you're running from the project root
   cd /path/to/multimodal-librarian
   python scripts/seed-all-sample-data.py
   ```

4. **Schema Errors**
   ```bash
   # Run database migrations first
   python -m src.multimodal_librarian.database.migrations
   ```

### Debugging

Use the `--verbose` flag for detailed logging:

```bash
python scripts/seed-all-sample-data.py --verbose
```

Check the application logs for database connection issues:

```bash
# View database logs
docker-compose -f docker-compose.local.yml logs postgres
docker-compose -f docker-compose.local.yml logs neo4j
docker-compose -f docker-compose.local.yml logs milvus
```

## Data Volumes

### Typical Data Sizes

With default settings, the scripts generate:

- **Users**: 10 accounts (~1KB each)
- **Documents**: 20 documents with ~1000 chunks (~500KB total)
- **Conversations**: 15 conversations with ~120 messages (~50KB total)
- **Analytics**: 30 days of data with ~3000 events (~2MB total)

**Total**: Approximately 3-5MB of sample data

### Quick Mode

Use `--quick` for smaller datasets during development:

- **Users**: 5 accounts
- **Documents**: 10 documents with fewer chunks
- **Conversations**: 8 conversations with shorter histories
- **Analytics**: 7 days of data with fewer events

**Total**: Approximately 1-2MB of sample data

## Integration with Development Workflow

### Makefile Integration

Add these targets to your `Makefile`:

```makefile
# Generate sample data
seed-data:
	python scripts/seed-all-sample-data.py

# Quick data setup
seed-data-quick:
	python scripts/seed-all-sample-data.py --quick

# Reset and regenerate data
seed-data-reset:
	python scripts/seed-all-sample-data.py --reset
```

### Docker Integration

Include data seeding in your development setup:

```bash
# Start services and generate data
make dev-local && make seed-data
```

### Testing Integration

Use the sample data for integration tests:

```python
# In your test setup
def setup_test_data():
    subprocess.run([
        "python", "scripts/seed-all-sample-data.py", 
        "--quick", "--reset"
    ])
```

## Security Considerations

### Development Only

⚠️ **Important**: These scripts are for local development only!

- Default passwords are weak and predictable
- Sample data includes test credentials
- No production security measures applied

### Sample Credentials

The generated sample users have predictable passwords:
- Pattern: `{username}123`
- Examples: `admin123`, `alice123`, `bob123`

**Never use these scripts or credentials in production!**

## Contributing

When adding new sample data scripts:

1. Follow the existing naming pattern: `seed-sample-{type}.py`
2. Include comprehensive argument parsing and help text
3. Add proper error handling and logging
4. Update the master script (`seed-all-sample-data.py`)
5. Document the new script in this README

### Script Template

```python
#!/usr/bin/env python3
"""
Sample {Type} Data Generator

Description of what this script generates.

Usage:
    python scripts/seed-sample-{type}.py [OPTIONS]
"""

import asyncio
import argparse
import logging
# ... other imports

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Sample{Type}Generator:
    """Generator for sample {type} data."""
    
    def __init__(self, config):
        self.config = config
        # ... initialization
    
    async def generate_{type}_data(self, **kwargs):
        """Generate sample {type} data."""
        # ... implementation
    
    async def close(self):
        """Close database connections."""
        # ... cleanup

async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Generate sample {type} data")
    # ... argument parsing
    
    generator = Sample{Type}Generator(config)
    try:
        # ... generation logic
        return 0
    except Exception as e:
        logger.error(f"Failed: {e}")
        return 1
    finally:
        await generator.close()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```