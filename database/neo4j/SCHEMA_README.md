# Neo4j Schema Initialization

This directory contains the complete schema initialization for the Multimodal Librarian knowledge graph using Neo4j.

## Overview

The Neo4j schema supports the application's knowledge graph functionality, providing:

- **Document Management**: Store and organize uploaded PDF documents
- **Concept Extraction**: Represent extracted concepts, entities, and topics
- **Knowledge Relationships**: Model semantic relationships between concepts
- **User Management**: Track users, conversations, and interactions
- **Vector Search Integration**: Link document chunks with vector embeddings
- **Analytics**: Store performance metrics and usage analytics

## Schema Components

### Node Types

| Label | Description | Required Properties | Optional Properties |
|-------|-------------|-------------------|-------------------|
| `Document` | Uploaded PDF documents | `id`, `title`, `filename` | `content`, `summary`, `created_at`, `file_size`, `page_count`, `status` |
| `Concept` | Extracted concepts and entities | `name`, `type` | `category`, `confidence`, `description`, `aliases` |
| `User` | Application users | `id`, `email` | `name`, `role`, `created_at`, `preferences` |
| `Conversation` | Chat conversations | `id` | `title`, `created_at`, `message_count`, `context` |
| `Chunk` | Document chunks for vector search | `id`, `content` | `position`, `page_number`, `embedding_id` |
| `Topic` | Hierarchical topic organization | `name` | `level`, `description`, `parent_topic` |
| `Metric` | Performance and analytics data | `name`, `value`, `timestamp` | `unit`, `metadata`, `source` |

### Relationship Types

| Type | Description | Source → Target | Properties |
|------|-------------|----------------|------------|
| `CONTAINS` | Document contains concept/chunk | `Document` → `Concept`, `Chunk` | `confidence`, `frequency`, `position` |
| `RELATED_TO` | Semantic concept relationships | `Concept` → `Concept` | `strength`, `relationship_type`, `bidirectional` |
| `OWNS` | User owns document | `User` → `Document` | `uploaded_at`, `permissions` |
| `PARTICIPATED_IN` | User participated in conversation | `User` → `Conversation` | `joined_at`, `role`, `message_count` |
| `ABOUT` | Conversation about document/concept | `Conversation` → `Document`, `Concept` | `relevance`, `context` |
| `HAS_CHUNK` | Document has chunk | `Document` → `Chunk` | `chunk_order`, `extraction_method` |
| `MENTIONS` | Chunk mentions concept | `Chunk` → `Concept` | `frequency`, `confidence`, `position` |
| `HAS_METRIC` | Entity has metric | `Document`, `Conversation`, `User` → `Metric` | `metric_type`, `collection_method` |
| `INCLUDES` | Hierarchical inclusion | `Topic`, `Concept` → `Topic`, `Concept` | `hierarchy_level`, `strength` |
| `APPLIES_TO` | Concept applies to domain | `Concept` → `Concept`, `Topic` | `applicability_score`, `context` |
| `ACCESSED` | User accessed document | `User` → `Document` | `accessed_at`, `access_type`, `duration` |

## Initialization Scripts

The schema is initialized through a series of Cypher scripts in the `init/` directory:

### 1. `00_schema_initialization.cypher`
**Primary schema setup script** - Creates the complete schema including:
- Unique constraints for all node types
- Performance indexes for common queries
- Full-text search indexes for content discovery
- Schema documentation nodes
- Relationship type documentation
- Validation rules

### 2. `01_verify_plugins.cypher`
**Plugin verification** - Ensures required Neo4j plugins are loaded:
- APOC (Awesome Procedures on Cypher) for extended functionality
- GDS (Graph Data Science) for graph algorithms
- Tests plugin functionality with sample operations

### 3. `02_create_constraints.cypher`
**Additional constraints** - Supplementary constraints and indexes:
- Legacy compatibility constraints
- Additional performance indexes
- Custom validation rules

### 4. `03_sample_data.cypher`
**Sample data for development** - Creates test data including:
- Sample users (developer and test users)
- Sample documents with metadata
- Sample concepts and relationships
- Sample conversations and chunks
- Sample metrics and analytics data
- Hierarchical topic structure for testing

## Usage

### Automatic Initialization

The schema is automatically initialized when starting the local development environment:

```bash
# Start local development (includes schema initialization)
make dev-local

# Or manually initialize after services are running
make db-init-neo4j
```

### Manual Initialization

For manual setup or troubleshooting:

```bash
# Initialize with sample data
./scripts/initialize-neo4j-schema.sh

# Initialize without sample data (production-like)
./scripts/initialize-neo4j-schema.sh --skip-sample-data

# Or use the comprehensive initialization script
./database/neo4j/init_schema.sh
```

### Docker Compose Integration

The schema initialization scripts are mounted into the Neo4j container:

```yaml
volumes:
  - ./database/neo4j/init:/var/lib/neo4j/init:ro
  - ./database/neo4j/init_schema.sh:/var/lib/neo4j/init_schema.sh:ro
```

## Verification

After initialization, verify the schema:

### 1. Check Constraints
```cypher
CALL db.constraints() YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
```

### 2. Check Indexes
```cypher
CALL db.indexes() YIELD name, type, entityType, labelsOrTypes, properties, state
WHERE state = "ONLINE"
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
```

### 3. View Schema Documentation
```cypher
MATCH (s:SchemaDoc)-[:DEFINES]->(item)
RETURN s.name as schema_name, 
       labels(item)[0] as item_type,
       item.label as label,
       item.description as description
ORDER BY item_type, label;
```

### 4. Check Sample Data
```cypher
// Count nodes by type
MATCH (n)
RETURN labels(n) as label, count(n) as count
ORDER BY count DESC;

// Count relationships by type
MATCH ()-[r]->()
RETURN type(r) as relationship_type, count(r) as count
ORDER BY count DESC;
```

## Schema Visualization

Access the Neo4j Browser at http://localhost:7474 and run:

```cypher
// Visualize the complete schema
CALL db.schema.visualization();

// View sample data relationships
MATCH (d:Document)-[r1:CONTAINS]->(c:Concept)-[r2:RELATED_TO]->(c2:Concept)
RETURN d, r1, c, r2, c2
LIMIT 25;
```

## Performance Considerations

### Indexes Created

The schema includes comprehensive indexing for optimal query performance:

- **Unique constraints** on all ID fields
- **Property indexes** on frequently queried fields (created_at, status, confidence)
- **Composite indexes** for multi-property queries
- **Full-text indexes** for content search across documents, concepts, and chunks

### Query Optimization

Common query patterns are optimized through:

1. **Concept lookups** by name and type
2. **Document searches** by title, content, and metadata
3. **User activity** tracking and analytics
4. **Relationship traversal** for multi-hop reasoning
5. **Temporal queries** using datetime indexes

### Memory Configuration

The Docker Compose configuration includes optimized memory settings:

```yaml
environment:
  - NEO4J_server_memory_heap_initial__size=512m
  - NEO4J_server_memory_heap_max__size=1G
  - NEO4J_server_memory_pagecache_size=512m
```

## Troubleshooting

### Common Issues

1. **Schema initialization fails**
   ```bash
   # Check Neo4j logs
   docker-compose -f docker-compose.local.yml logs neo4j
   
   # Verify Neo4j is ready
   docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password "RETURN 1"
   ```

2. **Plugin errors**
   ```bash
   # Verify APOC plugin
   docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password "CALL apoc.version()"
   
   # Verify GDS plugin
   docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password "CALL gds.version()"
   ```

3. **Performance issues**
   ```cypher
   // Check slow queries
   CALL dbms.listQueries() YIELD query, elapsedTimeMillis
   WHERE elapsedTimeMillis > 1000
   RETURN query, elapsedTimeMillis
   ORDER BY elapsedTimeMillis DESC;
   
   // Analyze query performance
   PROFILE MATCH (d:Document)-[:CONTAINS]->(c:Concept)
   WHERE c.name = "Machine Learning"
   RETURN d.title;
   ```

### Reset Schema

To completely reset the schema (WARNING: deletes all data):

```bash
# Stop services and remove volumes
docker-compose -f docker-compose.local.yml down -v

# Restart services (will reinitialize schema)
make dev-local
```

## Integration with Application

The schema integrates with the application through:

1. **Neo4j Client** (`src/multimodal_librarian/clients/neo4j_client.py`)
2. **Knowledge Graph Components** (`src/multimodal_librarian/components/knowledge_graph/`)
3. **Database Factory** (`src/multimodal_librarian/clients/database_factory.py`)

### Example Usage

```python
from multimodal_librarian.clients.neo4j_client import Neo4jClient

# Create client
client = Neo4jClient(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="ml_password"
)

# Connect and create a document
await client.connect()
doc_id = await client.create_node(
    ["Document"], 
    {
        "id": "doc_001",
        "title": "Sample Document",
        "filename": "sample.pdf"
    }
)

# Create a concept
concept_id = await client.create_node(
    ["Concept"],
    {
        "name": "Machine Learning",
        "type": "topic",
        "confidence": 0.95
    }
)

# Create relationship
rel_id = await client.create_relationship(
    doc_id, concept_id, "CONTAINS",
    {"confidence": 0.95, "extraction_method": "LLM"}
)
```

## Maintenance

### Regular Maintenance Tasks

1. **Monitor query performance**
2. **Update indexes** as query patterns evolve
3. **Clean up orphaned nodes** and relationships
4. **Backup graph data** regularly
5. **Update schema documentation** when adding new node types or relationships

### Backup and Restore

```bash
# Backup (included in make backup-local)
docker-compose -f docker-compose.local.yml exec neo4j neo4j-admin database backup neo4j --to-path=/backups

# Export to Cypher
docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p ml_password \
  "CALL apoc.export.cypher.all('/backups/knowledge_graph_backup.cypher')"
```

## Future Enhancements

Planned schema enhancements:

1. **Temporal relationships** with time-based properties
2. **Confidence propagation** through relationship chains
3. **External knowledge integration** (YAGO, ConceptNet)
4. **Advanced graph algorithms** for concept discovery
5. **Multi-language support** for international concepts
6. **Version control** for schema evolution