# Neo4j Re-enablement Requirements

## Overview
Re-enable Neo4j knowledge graph functionality for the multimodal-librarian-full-ml deployment. Neo4j was temporarily disabled during deployment fixes but needs to be restored to provide full knowledge graph capabilities.

## User Stories

### US-1: Neo4j Infrastructure Setup
**As a** system administrator  
**I want** Neo4j running on AWS infrastructure  
**So that** the application can store and query knowledge graphs  

**Acceptance Criteria:**
- Neo4j instance deployed on AWS EC2 with appropriate instance type
- Security groups configured for secure access from ECS tasks
- Backup and monitoring configured
- Neo4j accessible from full-ml ECS cluster
- Connection credentials stored in AWS Secrets Manager

### US-2: Application Integration
**As a** developer  
**I want** the application to connect to Neo4j  
**So that** knowledge graph features work correctly  

**Acceptance Criteria:**
- Neo4j client integrated into main_minimal.py
- Connection using credentials from `multimodal-librarian/full-ml/neo4j` secret
- Health check endpoint `/test/neo4j` returns connection status
- Error handling for Neo4j connection failures

### US-3: Knowledge Graph API Endpoints
**As a** user  
**I want** to interact with knowledge graphs through API  
**So that** I can create, query, and manage knowledge relationships  

**Acceptance Criteria:**
- `/api/knowledge-graph/create` endpoint for creating nodes/relationships
- `/api/knowledge-graph/query` endpoint for Cypher queries
- `/api/knowledge-graph/search` endpoint for semantic search
- Proper error handling and validation
- API documentation in OpenAPI/Swagger

### US-4: Knowledge Graph Processing
**As a** user  
**I want** documents to be automatically processed into knowledge graphs  
**So that** I can discover relationships and insights  

**Acceptance Criteria:**
- Document upload triggers knowledge graph extraction
- Entity recognition and relationship extraction
- Integration with existing PDF processing pipeline
- Knowledge graph visualization capabilities

## Technical Requirements

### Infrastructure Requirements
- **Neo4j Version**: 5.x (latest stable)
- **Instance Type**: t3.medium or larger (minimum 4GB RAM)
- **Storage**: 50GB EBS volume with backup enabled
- **Network**: VPC integration with full-ml cluster
- **Security**: Security groups allowing port 7687 (bolt) and 7474 (HTTP)

### Application Requirements
- **Neo4j Driver**: Python neo4j driver 5.x
- **Connection Pool**: Configured for ECS environment
- **Retry Logic**: Handle connection failures gracefully
- **Monitoring**: CloudWatch metrics for Neo4j operations

### Security Requirements
- **Authentication**: Username/password stored in Secrets Manager
- **Network Security**: VPC-only access, no public internet
- **Encryption**: TLS for all connections
- **IAM**: ECS task role with Secrets Manager access

## Current State Analysis

### Existing Assets
- ✅ Neo4j secret exists: `multimodal-librarian/full-ml/neo4j`
- ✅ ECS cluster: `multimodal-librarian-full-ml` is running
- ✅ VPC and networking infrastructure in place
- ✅ IAM roles configured for Secrets Manager access

### Missing Components
- ❌ Neo4j EC2 instance not deployed
- ❌ Neo4j client not integrated in application
- ❌ Knowledge graph API endpoints not implemented
- ❌ Document processing pipeline not connected to Neo4j

## Success Criteria

### Phase 1: Infrastructure (Week 1)
- Neo4j instance running and accessible
- Health check `/test/neo4j` returns success
- Connection from ECS tasks verified

### Phase 2: Basic Integration (Week 2)
- Neo4j client integrated in application
- Basic CRUD operations working
- API endpoints functional

### Phase 3: Advanced Features (Week 3)
- Document processing integration
- Knowledge graph visualization
- Performance optimization

## Dependencies
- Existing full-ml deployment must remain stable
- Database and Redis connectivity must not be affected
- Current application functionality must be preserved

## Risks and Mitigations
- **Risk**: Neo4j instance costs
  - **Mitigation**: Use cost-optimized instance type, implement auto-shutdown for dev
- **Risk**: Application complexity increase
  - **Mitigation**: Implement feature flags, graceful degradation
- **Risk**: Network connectivity issues
  - **Mitigation**: Thorough testing, connection retry logic

## Out of Scope
- Neo4j clustering (single instance for learning deployment)
- Advanced graph algorithms (focus on basic CRUD)
- Real-time graph streaming
- Multi-tenant graph isolation