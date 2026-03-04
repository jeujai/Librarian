# Neo4j Re-enablement Design

## Architecture Overview

### High-Level Architecture
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   ECS Cluster   │    │   Neo4j EC2      │    │  Secrets Mgr    │
│  (full-ml)      │◄──►│   Instance       │    │                 │
│                 │    │                  │    │  neo4j creds    │
│ - FastAPI App   │    │ - Neo4j 5.x      │    │                 │
│ - Neo4j Client  │    │ - Bolt: 7687     │    └─────────────────┘
│ - Health Checks │    │ - HTTP: 7474     │
└─────────────────┘    └──────────────────┘
         │                       │
         └───────────────────────┘
              VPC Network
```

### Component Design

#### 1. Neo4j Infrastructure
**EC2 Instance Configuration:**
- **Instance Type**: t3.medium (2 vCPU, 4GB RAM)
- **Storage**: 50GB gp3 EBS volume
- **OS**: Amazon Linux 2023
- **Neo4j Version**: 5.15.0 (latest stable)

**Security Groups:**
```yaml
Neo4jSecurityGroup:
  Ingress:
    - Port: 7687 (Bolt Protocol)
      Source: ECS Security Group
    - Port: 7474 (HTTP Interface)
      Source: ECS Security Group
    - Port: 22 (SSH)
      Source: Admin IP (optional)
```

**Installation Script:**
```bash
#!/bin/bash
# Install Java 17
sudo yum update -y
sudo yum install -y java-17-amazon-corretto

# Install Neo4j
wget -O - https://debian.neo4j.com/neotechnology.gpg.key | sudo apt-key add -
echo 'deb https://debian.neo4j.com stable latest' | sudo tee -a /etc/apt/sources.list.d/neo4j.list
sudo apt update
sudo apt install neo4j=1:5.15.0

# Configure Neo4j
sudo systemctl enable neo4j
sudo systemctl start neo4j
```

#### 2. Application Integration

**Neo4j Client Configuration:**
```python
from neo4j import GraphDatabase
import json
import boto3

class Neo4jClient:
    def __init__(self):
        self.driver = None
        self.connect()
    
    def connect(self):
        """Connect to Neo4j using AWS Secrets Manager credentials."""
        try:
            # Get Neo4j credentials
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            secret_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/full-ml/neo4j'
            )
            credentials = json.loads(secret_response['SecretString'])
            
            # Create driver
            uri = f"bolt://{credentials['host']}:{credentials['port']}"
            self.driver = GraphDatabase.driver(
                uri,
                auth=(credentials['username'], credentials['password']),
                max_connection_lifetime=30 * 60,  # 30 minutes
                max_connection_pool_size=50,
                connection_acquisition_timeout=60
            )
            
        except Exception as e:
            print(f"Failed to connect to Neo4j: {e}")
            self.driver = None
    
    def test_connection(self):
        """Test Neo4j connection."""
        if not self.driver:
            return False
        
        try:
            with self.driver.session() as session:
                result = session.run("RETURN 1 as test")
                return result.single()["test"] == 1
        except Exception:
            return False
    
    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
```

#### 3. API Endpoints Design

**Health Check Endpoint:**
```python
@app.get("/test/neo4j")
async def test_neo4j_connection():
    """Test Neo4j connectivity."""
    try:
        neo4j_client = Neo4jClient()
        if neo4j_client.test_connection():
            return {
                "status": "success",
                "database": "neo4j",
                "connection_test": "passed",
                "version": "5.15.0"
            }
        else:
            return {
                "status": "error",
                "database": "neo4j",
                "connection_test": "failed",
                "error": "Connection test failed"
            }
    except Exception as e:
        return {
            "status": "error",
            "database": "neo4j",
            "connection_test": "failed",
            "error": str(e)
        }
```

**Knowledge Graph API Router:**
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any

router = APIRouter(prefix="/api/knowledge-graph", tags=["knowledge-graph"])

class NodeCreate(BaseModel):
    label: str
    properties: Dict[str, Any]

class RelationshipCreate(BaseModel):
    from_node_id: int
    to_node_id: int
    relationship_type: str
    properties: Dict[str, Any] = {}

@router.post("/nodes")
async def create_node(node: NodeCreate):
    """Create a new node in the knowledge graph."""
    # Implementation here
    pass

@router.get("/nodes/{node_id}")
async def get_node(node_id: int):
    """Get a node by ID."""
    # Implementation here
    pass

@router.post("/relationships")
async def create_relationship(relationship: RelationshipCreate):
    """Create a relationship between nodes."""
    # Implementation here
    pass

@router.post("/query")
async def execute_cypher_query(query: str):
    """Execute a Cypher query."""
    # Implementation here
    pass
```

#### 4. Document Processing Integration

**Knowledge Graph Extraction Pipeline:**
```python
class KnowledgeGraphExtractor:
    def __init__(self, neo4j_client: Neo4jClient):
        self.neo4j_client = neo4j_client
    
    def extract_from_document(self, document_content: str, document_id: str):
        """Extract knowledge graph from document content."""
        # 1. Entity extraction using NLP
        entities = self.extract_entities(document_content)
        
        # 2. Relationship extraction
        relationships = self.extract_relationships(document_content, entities)
        
        # 3. Store in Neo4j
        self.store_knowledge_graph(entities, relationships, document_id)
    
    def extract_entities(self, content: str) -> List[Dict]:
        """Extract entities from text content."""
        # Simple implementation - can be enhanced with NLP libraries
        # For now, extract basic patterns
        entities = []
        # Implementation here
        return entities
    
    def extract_relationships(self, content: str, entities: List[Dict]) -> List[Dict]:
        """Extract relationships between entities."""
        relationships = []
        # Implementation here
        return relationships
    
    def store_knowledge_graph(self, entities: List[Dict], relationships: List[Dict], document_id: str):
        """Store extracted knowledge graph in Neo4j."""
        if not self.neo4j_client.driver:
            return
        
        with self.neo4j_client.driver.session() as session:
            # Create document node
            session.run(
                "CREATE (d:Document {id: $doc_id, created_at: datetime()})",
                doc_id=document_id
            )
            
            # Create entity nodes and relationships
            for entity in entities:
                session.run(
                    "CREATE (e:Entity {name: $name, type: $type}) "
                    "WITH e "
                    "MATCH (d:Document {id: $doc_id}) "
                    "CREATE (d)-[:CONTAINS]->(e)",
                    name=entity['name'],
                    type=entity['type'],
                    doc_id=document_id
                )
```

## Database Schema Design

### Neo4j Graph Schema
```cypher
// Document nodes
CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE;

// Entity nodes
CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE;

// Index for performance
CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type);
CREATE INDEX document_created IF NOT EXISTS FOR (d:Document) ON (d.created_at);

// Sample schema
(:Document {id: string, title: string, created_at: datetime})
(:Entity {name: string, type: string, confidence: float})
(:Person {name: string, role: string})
(:Organization {name: string, industry: string})
(:Concept {name: string, definition: string})

// Relationships
(:Document)-[:CONTAINS]->(:Entity)
(:Entity)-[:RELATED_TO]->(:Entity)
(:Person)-[:WORKS_FOR]->(:Organization)
(:Entity)-[:MENTIONED_IN]->(:Document)
```

## Deployment Strategy

### Phase 1: Infrastructure Setup
1. **Create Neo4j EC2 instance**
   - Launch t3.medium instance
   - Configure security groups
   - Install and configure Neo4j

2. **Update Secrets Manager**
   - Verify `multimodal-librarian/full-ml/neo4j` secret
   - Update with actual Neo4j instance details

3. **Test connectivity**
   - Verify ECS can reach Neo4j
   - Test authentication

### Phase 2: Application Integration
1. **Add Neo4j client to application**
   - Install neo4j Python driver
   - Add connection management
   - Implement health check

2. **Deploy and test**
   - Update ECS task definition
   - Deploy new version
   - Verify `/test/neo4j` endpoint

### Phase 3: API Implementation
1. **Implement knowledge graph APIs**
   - Basic CRUD operations
   - Query endpoints
   - Error handling

2. **Document processing integration**
   - Connect to existing PDF pipeline
   - Implement knowledge extraction
   - Test end-to-end flow

## Configuration Management

### Environment Variables
```bash
# Neo4j Configuration
NEO4J_ENABLED=true
NEO4J_SECRET_NAME=multimodal-librarian/full-ml/neo4j
NEO4J_CONNECTION_TIMEOUT=60
NEO4J_MAX_POOL_SIZE=50
```

### Feature Flags
```python
FEATURES = {
    "knowledge_graph": True,  # Enable Neo4j features
    "kg_document_processing": True,  # Auto-extract from documents
    "kg_visualization": False,  # Future feature
}
```

## Monitoring and Observability

### CloudWatch Metrics
- Neo4j connection count
- Query execution time
- Error rates
- Knowledge graph size metrics

### Health Checks
- Neo4j connectivity test
- Database query performance
- Memory usage monitoring

### Logging
- Neo4j connection events
- Query execution logs
- Error tracking and alerting

## Security Considerations

### Network Security
- VPC-only access (no public internet)
- Security groups restricting access to ECS cluster
- TLS encryption for all connections

### Authentication & Authorization
- Strong passwords stored in Secrets Manager
- Regular credential rotation
- Principle of least privilege for IAM roles

### Data Security
- Encryption at rest for EBS volumes
- Backup encryption
- Audit logging for sensitive operations

## Cost Optimization

### Instance Sizing
- Start with t3.medium (cost ~$30/month)
- Monitor usage and scale as needed
- Consider spot instances for development

### Storage Optimization
- Use gp3 volumes for better cost/performance
- Implement data retention policies
- Regular cleanup of unused data

### Development Optimizations
- Auto-shutdown for non-production environments
- Shared development instances
- Monitoring and alerting for cost thresholds