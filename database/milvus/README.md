# Milvus Configuration for Local Development

This directory contains configuration files for Milvus, the vector database used for semantic search and embeddings in local development.

## Quick Start

1. **Start services with admin tools profile:**
   ```bash
   docker-compose -f docker-compose.local.yml --profile admin-tools up -d
   ```

2. **Access Attu (Milvus Admin UI):**
   - URL: http://localhost:3000
   - Milvus Host: milvus
   - Milvus Port: 19530
   - No authentication required for local development

3. **Test the connection:**
   - Click "Connect" in Attu
   - You should see the Milvus instance information

## Configuration

### Connection Details

- **Milvus gRPC Port:** 19530 (Application connections)
- **Milvus Web UI Port:** 9091 (Health checks and metrics)
- **Attu Admin Port:** 3000 (Web administration interface)
- **MinIO Port:** 9000 (Object storage for Milvus)
- **MinIO Console:** 9001 (MinIO web interface)
- **etcd Port:** 2379 (Metadata storage)

### Dependencies

Milvus requires these supporting services:
- **etcd:** Metadata storage and service discovery
- **MinIO:** Object storage for vector data and indexes
- **Attu:** Web-based administration interface

## Attu Administration Interface

### Main Features

1. **Collection Management:** Create, view, and manage vector collections
2. **Data Operations:** Insert, query, and delete vectors
3. **Index Management:** Create and manage vector indexes
4. **System Monitoring:** View system status and performance metrics
5. **Query Interface:** Execute vector similarity searches

### Common Tasks

#### Create a Collection

1. Navigate to "Collections" in Attu
2. Click "Create Collection"
3. Configure collection parameters:
   - **Name:** `knowledge_chunks`
   - **Dimension:** `384` (for all-MiniLM-L6-v2 embeddings)
   - **Primary Key:** `id` (VARCHAR)
   - **Vector Field:** `embedding` (FLOAT_VECTOR)

#### Insert Vectors

1. Select your collection
2. Go to "Data" tab
3. Click "Insert Data"
4. Upload JSON file or use the form interface

#### Create Index

1. Select your collection
2. Go to "Index" tab
3. Click "Create Index"
4. Choose index parameters:
   - **Index Type:** `IVF_FLAT` (good for development)
   - **Metric Type:** `L2` or `COSINE`
   - **Parameters:** `nlist: 1024`

#### Search Vectors

1. Select your collection
2. Go to "Search" tab
3. Enter query vector or upload from file
4. Set search parameters (topK, search params)
5. Execute search

## Environment Variables

Customize Milvus settings in your `.env.local` file:

```bash
# Milvus Configuration
MILVUS_HOST=milvus
MILVUS_PORT=19530
MILVUS_COLLECTION_NAME=knowledge_chunks
MILVUS_INDEX_TYPE=IVF_FLAT
MILVUS_METRIC_TYPE=L2
MILVUS_NLIST=1024

# Attu Configuration
ATTU_PORT=3000

# MinIO Configuration (Milvus storage backend)
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_PORT=9000
MINIO_CONSOLE_PORT=9001
```

## Collection Schemas

The Multimodal Librarian uses predefined collection schemas to ensure consistency and optimal performance. Schemas are defined in `database/milvus/schemas.py` and automatically applied during collection creation.

### Available Collections

#### Default Collections (Created Automatically)

1. **knowledge_chunks** - Document text chunks with embeddings
   - **Purpose**: Store processed document chunks for semantic search
   - **Dimension**: 384 (sentence-transformers)
   - **Index**: IVF_FLAT with L2 distance
   - **Fields**: id, embedding, content, source_id, chunk_index, content_type, processing_metadata, timestamps

2. **document_embeddings** - Document-level embeddings
   - **Purpose**: Store whole-document embeddings for document similarity
   - **Dimension**: 384 (sentence-transformers)
   - **Index**: IVF_FLAT with COSINE distance
   - **Fields**: document_id, embedding, title, author, document_type, language, metadata, timestamps

3. **conversation_embeddings** - Chat message embeddings
   - **Purpose**: Store conversation messages for context-aware chat
   - **Dimension**: 384 (sentence-transformers)
   - **Index**: IVF_FLAT with L2 distance
   - **Fields**: message_id, embedding, content, conversation_id, user_id, message_type, metadata, timestamps

#### Optional Collections (Created On Demand)

4. **multimedia_embeddings** - Multimodal content embeddings
   - **Purpose**: Store embeddings for images, charts, and visual content
   - **Dimension**: 512 (CLIP embeddings)
   - **Index**: HNSW with COSINE distance
   - **Fields**: media_id, embedding, media_type, caption, source_document_id, technical_metadata, timestamps

### Schema Management

#### Automatic Schema Initialization

```bash
# Initialize all default collections
./database/milvus/init_schemas.sh

# Initialize specific collections
./database/milvus/init_schemas.sh --collections knowledge_chunks document_embeddings

# Force recreation of existing collections
./database/milvus/init_schemas.sh --force

# Validate existing schemas
./database/milvus/init_schemas.sh --validate
```

#### Python Schema Management

```python
from database.milvus.integration import integrate_schema_manager
from src.multimodal_librarian.clients.milvus_client import MilvusClient

# Create client with schema management
client = MilvusClient(host="localhost", port=19530)
await client.connect()

# Add schema management capabilities
integrate_schema_manager(client)

# Ensure collection exists with proper schema
await client.ensure_collection_with_schema("knowledge_chunks")

# Validate existing collection schema
is_valid, issues = await client.validate_collection_schema("knowledge_chunks")

# Set up all default collections
results = await client.ensure_default_collections()

# Get comprehensive schema summary
summary = await client.get_schema_summary()
```

#### Manual Schema Operations

```python
from database.milvus.schema_manager import MilvusSchemaManager

# Create schema manager
manager = MilvusSchemaManager(milvus_client)

# Ensure specific collection exists
await manager.ensure_collection_exists("knowledge_chunks")

# Validate all schemas
validation_results = await manager.validate_all_schemas()

# Get detailed schema information
schema_info = await manager.get_collection_info("knowledge_chunks")
```
```

## Python Client Usage

### Basic Operations

```python
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType

# Connect to Milvus
connections.connect("default", host="localhost", port="19530")

# Define collection schema
fields = [
    FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=255, is_primary=True),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=384),
    FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
    FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=255),
    FieldSchema(name="chunk_index", dtype=DataType.INT64),
]

schema = CollectionSchema(fields, "Knowledge chunks collection")
collection = Collection("knowledge_chunks", schema)

# Create index
index_params = {
    "metric_type": "L2",
    "index_type": "IVF_FLAT",
    "params": {"nlist": 1024}
}
collection.create_index("embedding", index_params)

# Insert data
entities = [
    ["chunk_1", "chunk_2"],  # ids
    [[0.1] * 384, [0.2] * 384],  # embeddings
    ["Sample text 1", "Sample text 2"],  # text
    ["doc_1", "doc_1"],  # document_ids
    [0, 1]  # chunk_indexes
]
collection.insert(entities)

# Search
search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
results = collection.search(
    data=[[0.1] * 384],  # query vector
    anns_field="embedding",
    param=search_params,
    limit=10,
    expr=None
)
```

## Performance Tuning

### Index Selection

- **IVF_FLAT:** Good balance of speed and accuracy for development
- **IVF_SQ8:** Memory-efficient, slightly lower accuracy
- **HNSW:** High accuracy, more memory usage
- **ANNOY:** Fast searches, good for read-heavy workloads

### Search Parameters

```python
# IVF_FLAT search parameters
search_params = {
    "metric_type": "L2",
    "params": {"nprobe": 10}  # Higher nprobe = better accuracy, slower search
}

# HNSW search parameters
search_params = {
    "metric_type": "L2", 
    "params": {"ef": 64}  # Higher ef = better accuracy, slower search
}
```

### Memory Management

- **Load Collection:** `collection.load()` - Load collection into memory
- **Release Collection:** `collection.release()` - Free memory
- **Flush:** `collection.flush()` - Persist data to disk

## Monitoring and Maintenance

### System Information

```python
from pymilvus import utility

# Check Milvus version
print(utility.get_server_version())

# List collections
print(utility.list_collections())

# Collection statistics
stats = utility.get_query_segment_info("knowledge_chunks")
print(stats)
```

### Health Checks

1. **Milvus Health:** http://localhost:9091/healthz
2. **Collection Status:** Check in Attu or via Python client
3. **etcd Health:** `docker-compose exec etcd etcdctl endpoint health`
4. **MinIO Health:** http://localhost:9000/minio/health/live

## Troubleshooting

### Cannot Connect to Milvus

1. **Check if Milvus is running:**
   ```bash
   docker-compose -f docker-compose.local.yml ps milvus
   ```

2. **Check Milvus logs:**
   ```bash
   docker-compose -f docker-compose.local.yml logs milvus
   ```

3. **Verify dependencies are running:**
   ```bash
   docker-compose -f docker-compose.local.yml ps etcd minio
   ```

### Attu Cannot Connect

1. **Check Attu logs:**
   ```bash
   docker-compose -f docker-compose.local.yml logs attu
   ```

2. **Verify Milvus is accessible:**
   ```bash
   curl http://localhost:9091/healthz
   ```

3. **Check network connectivity:**
   ```bash
   docker-compose -f docker-compose.local.yml exec attu ping milvus
   ```

### Performance Issues

1. **Check memory usage:**
   ```bash
   docker stats milvus
   ```

2. **Monitor collection load status:**
   ```python
   from pymilvus import utility
   print(utility.loading_progress("knowledge_chunks"))
   ```

3. **Optimize index parameters:**
   - Increase `nlist` for IVF indexes
   - Adjust `nprobe` for search accuracy vs speed
   - Consider different index types

### Data Issues

1. **Check collection schema:**
   ```python
   collection = Collection("knowledge_chunks")
   print(collection.schema)
   ```

2. **Verify data insertion:**
   ```python
   print(collection.num_entities)
   ```

3. **Check index status:**
   ```python
   print(collection.indexes)
   ```

## Backup and Recovery

### Export Collection Data

```python
# Export vectors to JSON
import json
from pymilvus import Collection

collection = Collection("knowledge_chunks")
results = collection.query(expr="", output_fields=["*"])

with open("knowledge_chunks_backup.json", "w") as f:
    json.dump(results, f, indent=2)
```

### Backup MinIO Data

```bash
# Backup MinIO data directory
docker-compose -f docker-compose.local.yml exec minio mc mirror /data /backups/minio-backup
```

### Restore Collection

```python
# Restore from JSON backup
import json
from pymilvus import Collection

with open("knowledge_chunks_backup.json", "r") as f:
    data = json.load(f)

collection = Collection("knowledge_chunks")
# Process and insert data back
```

## Integration with Application

The application connects to Milvus using the PyMilvus client:

- **Connection:** `pymilvus.connections.connect("default", host="milvus", port="19530")`
- **Collection Management:** Automatic collection creation and schema management
- **Vector Operations:** Insert embeddings, similarity search, data retrieval
- **Error Handling:** Connection retry logic and graceful degradation

### Sample Application Code

```python
from src.multimodal_librarian.clients.milvus_client import MilvusClient

# Initialize client
client = MilvusClient(host="milvus", port=19530)

# Create collection
await client.create_collection("knowledge_chunks", dimension=384)

# Insert vectors
vectors = [
    {"id": "chunk_1", "embedding": [0.1] * 384, "text": "Sample text"},
    {"id": "chunk_2", "embedding": [0.2] * 384, "text": "Another text"}
]
await client.insert_vectors(vectors)

# Search similar vectors
results = await client.search_vectors(
    query_vector=[0.15] * 384,
    collection_name="knowledge_chunks",
    top_k=10
)
```

## Best Practices

### Collection Design

1. **Use meaningful collection names** that reflect the data type
2. **Choose appropriate dimensions** based on your embedding model
3. **Include metadata fields** for filtering and retrieval
4. **Use consistent ID formats** for easier management

### Index Strategy

1. **Create indexes after bulk insertion** for better performance
2. **Choose index type based on use case:**
   - Development: IVF_FLAT
   - Production: HNSW or IVF_PQ
3. **Monitor index build progress** for large collections
4. **Rebuild indexes** when collection size changes significantly

### Query Optimization

1. **Use expression filtering** to reduce search space
2. **Batch queries** when possible for better throughput
3. **Cache frequently used results** in application layer
4. **Monitor query performance** and adjust parameters

### Maintenance

1. **Regular data compaction** to optimize storage
2. **Monitor memory usage** and adjust load/release cycles
3. **Backup important collections** regularly
4. **Update Milvus version** for performance improvements