# Knowledge Graph Test Data Generation

This directory contains scripts for generating comprehensive knowledge graph test data for local development. The knowledge graph provides semantic relationships between concepts, documents, and other entities in the multimodal librarian system.

## Overview

The knowledge graph test data includes:

1. **Sample Concepts and Relationships** - Core concepts from AI/ML domains with semantic relationships
2. **Document-Concept Associations** - Links between uploaded documents and relevant concepts
3. **Multi-Hop Relationship Examples** - Complex relationship patterns for advanced graph queries

## Scripts

### Main Generation Script

- **`seed-all-knowledge-graph-data.py`** - Orchestrates complete knowledge graph generation
  - Runs all generators in the correct order
  - Provides comprehensive progress reporting
  - Handles errors gracefully

### Individual Generators

- **`seed-sample-knowledge-graph.py`** - Creates concepts and basic relationships
- **`seed-document-concept-associations.py`** - Links documents to concepts
- **`seed-multi-hop-relationships.py`** - Creates complex relationship patterns

## Quick Start

### Prerequisites

1. **Neo4j running locally**:
   ```bash
   docker-compose -f docker-compose.local.yml up neo4j -d
   ```

2. **Sample documents and users** (optional but recommended):
   ```bash
   python scripts/seed-sample-users.py --count 10
   python scripts/seed-sample-documents.py --count 20 --with-chunks
   ```

### Generate Complete Knowledge Graph

```bash
# Generate with default settings (50 concepts)
python scripts/seed-all-knowledge-graph-data.py

# Generate with custom settings
python scripts/seed-all-knowledge-graph-data.py --concepts 100 --reset --verbose

# Generate individual components
python scripts/seed-sample-knowledge-graph.py --concepts 50 --with-relationships
python scripts/seed-document-concept-associations.py --max-associations 8
python scripts/seed-multi-hop-relationships.py --max-depth 4
```

## Generated Data Structure

### Concepts

The knowledge graph includes concepts from multiple domains:

- **Machine Learning**: Neural Networks, Deep Learning, Supervised Learning, etc.
- **Natural Language Processing**: Tokenization, NER, Sentiment Analysis, etc.
- **Computer Vision**: Image Classification, Object Detection, CNNs, etc.
- **Data Science**: Statistics, Data Mining, Visualization, etc.

Each concept includes:
- Name, type, category, domain
- Description and confidence score
- Aliases and external IDs
- Creation metadata

### Relationships

Multiple relationship types connect concepts:

- **Hierarchical**: `IS_TYPE_OF`, `IS_SUBSET_OF`, `INCLUDES`
- **Functional**: `USED_IN`, `USED_FOR`, `APPLIED_TO`
- **Dependency**: `PREREQUISITE_FOR`, `REQUIRES`, `ENABLES`
- **Similarity**: `RELATED_TO`, `SIMILAR_TO`
- **Problem-Solution**: `SOLVED_BY`, `PREVENTS`, `IMPROVES`

### Document Associations

Documents are linked to concepts through:

- **CONTAINS** relationships (document contains concept)
- **MENTIONS** relationships (chunk mentions concept)
- **HAS_CHUNK** relationships (document has chunks)

### Multi-Hop Patterns

Complex patterns enable advanced queries:

- **Taxonomic Hierarchies**: AI → ML → Deep Learning → CNN → ResNet
- **Application Chains**: Data → Preprocessing → Feature Engineering → ML → Prediction
- **Problem-Solution Chains**: Overfitting → Regularization → Dropout → Neural Networks
- **Workflow Pipelines**: Text → Tokenization → POS Tagging → NER → Semantic Analysis

## Exploration and Queries

### Neo4j Browser

Access the Neo4j Browser at http://localhost:7474

**Default Credentials:**
- Username: `neo4j`
- Password: `ml_password` (or your configured password)

### Sample Queries

#### Basic Exploration

```cypher
// View all concept domains
MATCH (c:Concept) 
RETURN c.domain, count(c) as concept_count 
ORDER BY concept_count DESC

// Find concepts by type
MATCH (c:Concept {type: 'algorithm'}) 
RETURN c.name, c.domain, c.description 
LIMIT 10

// View relationship types
MATCH ()-[r]->() 
RETURN type(r) as relationship_type, count(r) as count 
ORDER BY count DESC
```

#### Document-Concept Associations

```cypher
// Documents and their concepts
MATCH (d:Document)-[:CONTAINS]->(c:Concept)
RETURN d.title, collect(c.name) as concepts
LIMIT 10

// Most referenced concepts
MATCH (d:Document)-[:CONTAINS]->(c:Concept)
RETURN c.name, c.domain, count(d) as document_count
ORDER BY document_count DESC
LIMIT 10

// Chunk-level concept mentions
MATCH (ch:Chunk)-[:MENTIONS]->(c:Concept)
RETURN ch.page_number, c.name, ch.content[0..100] + "..."
LIMIT 10
```

#### Multi-Hop Relationships

```cypher
// Find learning paths (2-4 hops)
MATCH path = (start:Concept)-[:PREREQUISITE_FOR|ENABLES*2..4]->(end:Concept)
WHERE start.name = 'Statistics' AND end.name = 'Deep Learning'
RETURN [n in nodes(path) | n.name] as learning_path, length(path) as steps
ORDER BY steps
LIMIT 5

// Cross-domain connections
MATCH path = (c1:Concept)-[*2..3]-(c2:Concept)
WHERE c1.domain = 'machine_learning' AND c2.domain = 'natural_language_processing'
RETURN c1.name, c2.name, length(path) as distance
ORDER BY distance
LIMIT 10

// Topic hierarchy exploration
MATCH path = (t:Topic)-[:INCLUDES*1..3]->(c:Concept)
RETURN t.name as topic, t.level, collect(c.name) as concepts
ORDER BY t.level, t.name
```

#### Advanced Analysis

```cypher
// Find concept clusters (highly connected concepts)
MATCH (c:Concept)-[r]-(connected:Concept)
WITH c, count(connected) as connections
WHERE connections > 5
RETURN c.name, c.domain, connections
ORDER BY connections DESC
LIMIT 10

// Inferred relationship analysis
MATCH ()-[r]->()
WHERE r.source = 'multi_hop_inference'
RETURN r.inference_pattern, count(r) as inferred_count
ORDER BY inferred_count DESC

// Document coverage analysis
MATCH (d:Document)
OPTIONAL MATCH (d)-[:CONTAINS]->(c:Concept)
RETURN d.title, d.subject, count(c) as concept_count
ORDER BY concept_count DESC
LIMIT 10
```

## Configuration

### Environment Variables

Set in `.env.local`:

```bash
# Neo4j Configuration
ML_NEO4J_HOST=localhost
ML_NEO4J_PORT=7687
ML_NEO4J_USER=neo4j
ML_NEO4J_PASSWORD=ml_password

# Database Type
ML_DATABASE_TYPE=local
```

### Generation Parameters

Customize generation through command-line arguments:

```bash
# Concept count (default: 50)
--concepts 100

# Reset existing data
--reset

# Enable verbose logging
--verbose

# Max associations per document (default: 8)
--max-associations 10

# Max relationship depth (default: 4)
--max-depth 5
```

## Troubleshooting

### Common Issues

1. **Neo4j Connection Failed**
   ```bash
   # Check if Neo4j is running
   docker-compose -f docker-compose.local.yml ps neo4j
   
   # Start Neo4j if not running
   docker-compose -f docker-compose.local.yml up neo4j -d
   
   # Check logs
   docker-compose -f docker-compose.local.yml logs neo4j
   ```

2. **No Documents Found**
   ```bash
   # Generate sample documents first
   python scripts/seed-sample-documents.py --count 20 --with-chunks
   ```

3. **Memory Issues**
   ```bash
   # Reduce concept count
   python scripts/seed-all-knowledge-graph-data.py --concepts 25
   
   # Or generate components separately
   python scripts/seed-sample-knowledge-graph.py --concepts 30
   ```

4. **Authentication Errors**
   ```bash
   # Check Neo4j credentials in .env.local
   # Default: neo4j/ml_password
   
   # Reset Neo4j password if needed
   docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p neo4j "ALTER CURRENT USER SET PASSWORD FROM 'neo4j' TO 'ml_password'"
   ```

### Performance Tips

1. **Batch Processing**: Scripts process data in batches to avoid memory issues
2. **Connection Pooling**: Neo4j client uses connection pooling for efficiency
3. **Incremental Generation**: Run individual scripts to build data incrementally
4. **Index Usage**: Neo4j indexes are created for optimal query performance

### Data Validation

```bash
# Check data integrity
python -c "
import asyncio
from scripts.seed_sample_knowledge_graph import SampleKnowledgeGraphGenerator
from multimodal_librarian.config.local_config import LocalDatabaseConfig

async def check():
    config = LocalDatabaseConfig()
    gen = SampleKnowledgeGraphGenerator(config)
    neo4j = await gen.factory.get_graph_client()
    await neo4j.connect()
    
    # Check concept count
    result = await neo4j.execute_query('MATCH (c:Concept) RETURN count(c) as count')
    print(f'Concepts: {result[0][\"count\"]}')
    
    # Check relationship count  
    result = await neo4j.execute_query('MATCH ()-[r]->() RETURN count(r) as count')
    print(f'Relationships: {result[0][\"count\"]}')
    
    await neo4j.disconnect()
    await gen.close()

asyncio.run(check())
"
```

## Integration with Application

The generated knowledge graph integrates with the multimodal librarian application through:

1. **Concept Search**: Find concepts related to user queries
2. **Document Enhancement**: Enrich documents with semantic concepts
3. **Recommendation Engine**: Suggest related concepts and documents
4. **Query Expansion**: Expand user queries using concept relationships
5. **Knowledge Discovery**: Enable multi-hop reasoning and inference

## Data Schema

### Node Types

- **Concept**: Core knowledge concepts with properties
- **Document**: Uploaded documents with metadata
- **Chunk**: Document chunks for granular associations
- **Topic**: Hierarchical topic organization

### Relationship Types

- **CONTAINS**: Document contains concept
- **MENTIONS**: Chunk mentions concept
- **HAS_CHUNK**: Document has chunk
- **IS_TYPE_OF**: Taxonomic relationship
- **USED_IN**: Usage relationship
- **PREREQUISITE_FOR**: Dependency relationship
- **RELATED_TO**: General semantic relationship
- **INCLUDES**: Hierarchical inclusion
- **BELONGS_TO**: Topic membership

## Future Enhancements

1. **Dynamic Concept Extraction**: Extract concepts from document content
2. **Semantic Similarity**: Use embeddings for concept similarity
3. **Temporal Relationships**: Track concept evolution over time
4. **User Interactions**: Incorporate user behavior into the graph
5. **External Knowledge**: Link to external knowledge bases (Wikipedia, DBpedia)
6. **Graph Analytics**: Implement centrality and community detection algorithms