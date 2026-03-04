# Neo4j Configuration for Local Development

This directory contains configuration files for Neo4j, the graph database used for knowledge graph operations in local development.

## Quick Start

1. **Start services:**
   ```bash
   docker-compose -f docker-compose.local.yml up -d neo4j
   ```

2. **Access Neo4j Browser:**
   - URL: http://localhost:7474
   - Username: neo4j
   - Password: ml_password
   - Connection URL: bolt://localhost:7687

3. **Test the connection:**
   ```cypher
   RETURN "Hello, Neo4j!" as greeting
   ```

## Configuration

### Connection Details

- **HTTP Port:** 7474 (Neo4j Browser)
- **Bolt Port:** 7687 (Application connections)
- **Backup Port:** 6362 (Database backups)
- **Username:** neo4j
- **Password:** ml_password (configurable via `NEO4J_PASSWORD`)

### Installed Plugins

- **APOC (Awesome Procedures on Cypher):** Extended functionality and procedures
- **Graph Data Science (GDS):** Graph algorithms and analytics

### Memory Configuration

- **Heap Initial Size:** 512MB
- **Heap Max Size:** 1GB
- **Page Cache Size:** 512MB

## Neo4j Browser Usage

### Basic Navigation

1. **Connect:** Enter credentials on the connection screen
2. **Query Editor:** Write Cypher queries in the top panel
3. **Results:** View results in graph or table format
4. **Sidebar:** Access guides, favorites, and database information

### Essential Cypher Queries

#### View Database Schema
```cypher
CALL db.schema.visualization()
```

#### List All Node Labels
```cypher
CALL db.labels()
```

#### List All Relationship Types
```cypher
CALL db.relationshipTypes()
```

#### Count Nodes by Label
```cypher
MATCH (n)
RETURN labels(n) as label, count(n) as count
ORDER BY count DESC
```

#### View Sample Data
```cypher
MATCH (n)
RETURN n
LIMIT 25
```

### Knowledge Graph Queries

#### Find Documents and Their Concepts
```cypher
MATCH (d:Document)-[:CONTAINS]->(c:Concept)
RETURN d.title, collect(c.name) as concepts
LIMIT 10
```

#### Find Related Concepts
```cypher
MATCH (c1:Concept)-[:RELATED_TO]-(c2:Concept)
WHERE c1.name = "Machine Learning"
RETURN c1, c2
```

#### Multi-hop Concept Relationships
```cypher
MATCH path = (c1:Concept)-[:RELATED_TO*1..3]-(c2:Concept)
WHERE c1.name = "Neural Networks"
RETURN path
LIMIT 10
```

## APOC Procedures

### Data Import/Export

#### Export Graph to JSON
```cypher
CALL apoc.export.json.all("knowledge_graph.json", {})
```

#### Import Data from JSON
```cypher
CALL apoc.load.json("file:///knowledge_graph.json")
YIELD value
RETURN value
```

### Text Processing

#### Extract Keywords from Text
```cypher
CALL apoc.nlp.aws.entities.stream([{text: "Your text here"}], {
  key: "your-aws-key",
  secret: "your-aws-secret"
})
YIELD value
RETURN value
```

## Graph Data Science (GDS)

### Create Graph Projection
```cypher
CALL gds.graph.project(
  'knowledge-graph',
  'Concept',
  'RELATED_TO'
)
```

### Run PageRank Algorithm
```cypher
CALL gds.pageRank.stream('knowledge-graph')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS concept, score
ORDER BY score DESC
LIMIT 10
```

### Community Detection
```cypher
CALL gds.louvain.stream('knowledge-graph')
YIELD nodeId, communityId
RETURN gds.util.asNode(nodeId).name AS concept, communityId
ORDER BY communityId
```

## Environment Variables

Customize Neo4j settings in your `.env.local` file:

```bash
# Neo4j Configuration
NEO4J_HOST=neo4j
NEO4J_PORT=7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-secure-password
NEO4J_HTTP_PORT=7474
NEO4J_BACKUP_PORT=6362

# Memory Settings (optional)
NEO4J_HEAP_INITIAL_SIZE=512m
NEO4J_HEAP_MAX_SIZE=1G
NEO4J_PAGE_CACHE_SIZE=512m
```

## Data Management

### Backup Database

#### Using Neo4j Admin (inside container)
```bash
docker-compose -f docker-compose.local.yml exec neo4j neo4j-admin database backup neo4j --to-path=/backups
```

#### Using APOC Export
```cypher
CALL apoc.export.cypher.all("/backups/knowledge_graph_backup.cypher", {
  format: "cypher-shell"
})
```

### Restore Database

#### From Backup
```bash
docker-compose -f docker-compose.local.yml exec neo4j neo4j-admin database restore neo4j --from-path=/backups
```

#### From Cypher File
```cypher
CALL apoc.cypher.runFile("/backups/knowledge_graph_backup.cypher")
```

### Clear All Data
```cypher
MATCH (n)
DETACH DELETE n
```

## Performance Monitoring

### Database Statistics
```cypher
CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Store file sizes")
YIELD attributes
RETURN attributes
```

### Query Performance
```cypher
CALL dbms.listQueries()
YIELD query, elapsedTimeMillis, allocatedBytes
WHERE elapsedTimeMillis > 1000
RETURN query, elapsedTimeMillis, allocatedBytes
ORDER BY elapsedTimeMillis DESC
```

### Memory Usage
```cypher
CALL dbms.queryJmx("java.lang:type=Memory")
YIELD attributes
RETURN attributes.HeapMemoryUsage, attributes.NonHeapMemoryUsage
```

## Troubleshooting

### Cannot Connect to Neo4j Browser

1. **Check if Neo4j is running:**
   ```bash
   docker-compose -f docker-compose.local.yml ps neo4j
   ```

2. **Check Neo4j logs:**
   ```bash
   docker-compose -f docker-compose.local.yml logs neo4j
   ```

3. **Verify ports are accessible:**
   ```bash
   curl http://localhost:7474
   ```

### Authentication Issues

1. **Reset password:**
   ```bash
   docker-compose -f docker-compose.local.yml exec neo4j cypher-shell -u neo4j -p neo4j "ALTER CURRENT USER SET PASSWORD FROM 'neo4j' TO 'ml_password'"
   ```

2. **Check authentication configuration:**
   ```bash
   docker-compose -f docker-compose.local.yml exec neo4j cat /var/lib/neo4j/conf/neo4j.conf | grep auth
   ```

### Plugin Issues

1. **Verify APOC installation:**
   ```cypher
   CALL apoc.help("apoc")
   ```

2. **Verify GDS installation:**
   ```cypher
   CALL gds.version()
   ```

3. **Check plugin directory:**
   ```bash
   docker-compose -f docker-compose.local.yml exec neo4j ls -la /var/lib/neo4j/plugins/
   ```

### Performance Issues

1. **Check memory usage:**
   ```cypher
   CALL dbms.queryJmx("java.lang:type=Memory") YIELD attributes
   RETURN attributes.HeapMemoryUsage
   ```

2. **Analyze slow queries:**
   ```cypher
   CALL dbms.listQueries() YIELD query, elapsedTimeMillis
   WHERE elapsedTimeMillis > 1000
   RETURN query, elapsedTimeMillis
   ORDER BY elapsedTimeMillis DESC
   ```

3. **Create indexes for better performance:**
   ```cypher
   CREATE INDEX concept_name_index FOR (c:Concept) ON (c.name)
   CREATE INDEX document_title_index FOR (d:Document) ON (d.title)
   ```

## Integration with Application

The application connects to Neo4j using the Bolt protocol:

- **Connection URI:** `bolt://neo4j:7687`
- **Driver:** Neo4j Python Driver
- **Connection Pool:** Managed by the driver
- **Transaction Management:** Automatic retry and session management

### Sample Application Queries

#### Create Document Node
```python
def create_document(tx, doc_id, title):
    return tx.run(
        "CREATE (d:Document {id: $doc_id, title: $title}) RETURN d",
        doc_id=doc_id, title=title
    )
```

#### Find Related Concepts
```python
def find_related_concepts(tx, concept_name, max_hops=2):
    return tx.run(
        "MATCH path = (c1:Concept {name: $name})-[:RELATED_TO*1..$max_hops]-(c2:Concept) "
        "RETURN c2.name as related_concept, length(path) as distance "
        "ORDER BY distance, c2.name",
        name=concept_name, max_hops=max_hops
    )
```

## Best Practices

### Query Optimization

1. **Use PROFILE/EXPLAIN** to analyze query performance
2. **Create appropriate indexes** for frequently queried properties
3. **Limit result sets** with LIMIT clauses
4. **Use parameters** instead of string concatenation

### Data Modeling

1. **Keep node properties simple** and use relationships for complex associations
2. **Use meaningful labels** and relationship types
3. **Normalize data** to avoid duplication
4. **Consider query patterns** when designing the schema

### Maintenance

1. **Regular backups** of important data
2. **Monitor query performance** and optimize slow queries
3. **Update plugins** regularly for security and features
4. **Clean up unused data** periodically