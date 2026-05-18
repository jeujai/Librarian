# Neo4j Re-enablement Implementation Tasks

## Phase 1: Infrastructure Setup (Week 1)

### Task 1.1: Neo4j EC2 Instance Deployment
**Priority**: High  
**Estimated Time**: 4 hours  
**Dependencies**: None  

**Subtasks:**
- [ ] Create EC2 instance (t3.medium) in existing VPC
- [ ] Configure security groups for Neo4j ports (7687, 7474)
- [ ] Install Java 17 and Neo4j 5.15.0
- [ ] Configure Neo4j for production use
- [ ] Set up EBS volume with backup enabled
- [ ] Test Neo4j installation and basic functionality

**Acceptance Criteria:**
- Neo4j instance running and accessible within VPC
- Security groups properly configured
- Neo4j web interface accessible from ECS cluster
- Basic Cypher queries working

**Files to Create/Modify:**
- `infrastructure/neo4j/neo4j-instance.tf` (if using Terraform)
- `scripts/setup-neo4j-instance.sh`
- `scripts/test-neo4j-connectivity.py`

### Task 1.2: Update AWS Secrets Manager
**Priority**: High  
**Estimated Time**: 1 hour  
**Dependencies**: Task 1.1  

**Subtasks:**
- [ ] Verify existing `multimodal-librarian/full-ml/neo4j` secret
- [ ] Update secret with actual Neo4j instance details
- [ ] Test secret retrieval from ECS environment
- [ ] Document secret structure

**Acceptance Criteria:**
- Secret contains correct Neo4j connection details
- ECS tasks can retrieve secret successfully
- Connection parameters are valid

**Files to Create/Modify:**
- `scripts/update-neo4j-secret.py`
- `docs/secrets-management.md`

### Task 1.3: Network Connectivity Testing
**Priority**: High  
**Estimated Time**: 2 hours  
**Dependencies**: Task 1.1, 1.2  

**Subtasks:**
- [ ] Test connectivity from ECS cluster to Neo4j
- [ ] Verify security group rules
- [ ] Test authentication with stored credentials
- [ ] Document network configuration

**Acceptance Criteria:**
- ECS tasks can connect to Neo4j on port 7687
- Authentication works with Secrets Manager credentials
- Network latency is acceptable (<10ms within VPC)

**Files to Create/Modify:**
- `scripts/test-neo4j-network.py`
- `docs/network-configuration.md`

## Phase 2: Application Integration (Week 2)

### Task 2.1: Neo4j Client Implementation
**Priority**: High  
**Estimated Time**: 6 hours  
**Dependencies**: Phase 1 complete  

**Subtasks:**
- [ ] Add neo4j Python driver to requirements
- [ ] Implement Neo4jClient class with connection management
- [ ] Add connection pooling and retry logic
- [ ] Implement graceful error handling
- [ ] Add connection health checks

**Acceptance Criteria:**
- Neo4j client connects successfully using Secrets Manager
- Connection pooling works correctly
- Proper error handling for connection failures
- Health check method returns accurate status

**Files to Create/Modify:**
- `requirements-full-ml.txt` (add neo4j driver)
- `src/multimodal_librarian/clients/neo4j_client.py`
- `src/multimodal_librarian/config/neo4j_config.py`

### Task 2.2: Health Check Integration
**Priority**: High  
**Estimated Time**: 2 hours  
**Dependencies**: Task 2.1  

**Subtasks:**
- [ ] Add `/test/neo4j` endpoint to main_minimal.py
- [ ] Implement Neo4j connection test
- [ ] Update overall health check to include Neo4j
- [ ] Add Neo4j status to features endpoint

**Acceptance Criteria:**
- `/test/neo4j` returns connection status
- Overall health check includes Neo4j status
- Features endpoint shows knowledge_graph: true
- Error responses are properly formatted

**Files to Create/Modify:**
- `src/multimodal_librarian/main_minimal.py`

### Task 2.3: Basic CRUD Operations
**Priority**: Medium  
**Estimated Time**: 4 hours  
**Dependencies**: Task 2.1  

**Subtasks:**
- [ ] Implement basic node creation/retrieval
- [ ] Implement relationship creation/retrieval
- [ ] Add basic Cypher query execution
- [ ] Implement error handling and validation

**Acceptance Criteria:**
- Can create and retrieve nodes
- Can create and retrieve relationships
- Basic Cypher queries execute successfully
- Proper error handling for invalid queries

**Files to Create/Modify:**
- `src/multimodal_librarian/services/knowledge_graph_service.py`

## Phase 3: API Implementation (Week 2-3)

### Task 3.1: Knowledge Graph API Router
**Priority**: Medium  
**Estimated Time**: 6 hours  
**Dependencies**: Task 2.3  

**Subtasks:**
- [ ] Create knowledge graph API router
- [ ] Implement node CRUD endpoints
- [ ] Implement relationship CRUD endpoints
- [ ] Add Cypher query endpoint
- [ ] Add proper request/response models

**Acceptance Criteria:**
- All CRUD endpoints working correctly
- Proper request validation
- Comprehensive error handling
- OpenAPI documentation generated

**Files to Create/Modify:**
- `src/multimodal_librarian/api/routers/knowledge_graph.py`
- `src/multimodal_librarian/api/models/knowledge_graph.py`

### Task 3.2: API Integration with Main App
**Priority**: Medium  
**Estimated Time**: 2 hours  
**Dependencies**: Task 3.1  

**Subtasks:**
- [ ] Add knowledge graph router to main app
- [ ] Update feature flags
- [ ] Test all endpoints
- [ ] Update API documentation

**Acceptance Criteria:**
- Knowledge graph endpoints accessible
- Feature flags properly configured
- All endpoints return expected responses
- API documentation is complete

**Files to Create/Modify:**
- `src/multimodal_librarian/main_minimal.py`

### Task 3.3: Search and Query Endpoints
**Priority**: Low  
**Estimated Time**: 4 hours  
**Dependencies**: Task 3.1  

**Subtasks:**
- [ ] Implement semantic search endpoint
- [ ] Add graph traversal queries
- [ ] Implement entity search
- [ ] Add query optimization

**Acceptance Criteria:**
- Search endpoints return relevant results
- Graph traversal works correctly
- Performance is acceptable
- Results are properly formatted

**Files to Create/Modify:**
- `src/multimodal_librarian/services/graph_search_service.py`

## Phase 4: Document Processing Integration (Week 3)

### Task 4.1: Knowledge Extraction Pipeline
**Priority**: Medium  
**Estimated Time**: 8 hours  
**Dependencies**: Task 3.2  

**Subtasks:**
- [ ] Implement basic entity extraction
- [ ] Add relationship extraction
- [ ] Create document-to-graph pipeline
- [ ] Integrate with existing PDF processing

**Acceptance Criteria:**
- Documents are processed into knowledge graphs
- Entities and relationships are extracted
- Integration with PDF pipeline works
- Knowledge graphs are stored correctly

**Files to Create/Modify:**
- `src/multimodal_librarian/components/knowledge_graph/extractor.py`
- `src/multimodal_librarian/services/document_processing_service.py`

### Task 4.2: Automatic Processing Integration
**Priority**: Low  
**Estimated Time**: 4 hours  
**Dependencies**: Task 4.1  

**Subtasks:**
- [ ] Add knowledge graph processing to document upload
- [ ] Implement background processing
- [ ] Add processing status tracking
- [ ] Create processing queue

**Acceptance Criteria:**
- Documents automatically processed on upload
- Processing happens in background
- Status can be tracked
- Queue handles multiple documents

**Files to Create/Modify:**
- `src/multimodal_librarian/services/processing_service.py`
- `src/multimodal_librarian/api/routers/documents.py`

## Phase 5: Testing and Deployment (Week 3-4)

### Task 5.1: Comprehensive Testing
**Priority**: High  
**Estimated Time**: 6 hours  
**Dependencies**: All previous tasks  

**Subtasks:**
- [ ] Create unit tests for Neo4j client
- [ ] Add integration tests for API endpoints
- [ ] Test document processing pipeline
- [ ] Performance testing
- [ ] Error scenario testing

**Acceptance Criteria:**
- All tests pass
- Code coverage >80%
- Performance meets requirements
- Error handling works correctly

**Files to Create/Modify:**
- `tests/clients/test_neo4j_client.py`
- `tests/api/test_knowledge_graph.py`
- `tests/integration/test_neo4j_integration.py`

### Task 5.2: Deployment and Monitoring
**Priority**: High  
**Estimated Time**: 4 hours  
**Dependencies**: Task 5.1  

**Subtasks:**
- [ ] Update ECS task definition with Neo4j dependencies
- [ ] Deploy to full-ml cluster
- [ ] Set up CloudWatch monitoring
- [ ] Configure alerts
- [ ] Test production deployment

**Acceptance Criteria:**
- Deployment successful
- All health checks pass
- Monitoring is active
- Alerts are configured

**Files to Create/Modify:**
- `full-ml-task-def.json`
- `scripts/deploy-full-ml-with-neo4j.sh`
- `monitoring/neo4j-dashboard.json`

### Task 5.3: Documentation and Training
**Priority**: Medium  
**Estimated Time**: 4 hours  
**Dependencies**: Task 5.2  

**Subtasks:**
- [ ] Update API documentation
- [ ] Create user guide for knowledge graph features
- [ ] Document deployment procedures
- [ ] Create troubleshooting guide

**Acceptance Criteria:**
- Documentation is complete and accurate
- User guide covers all features
- Deployment procedures are documented
- Troubleshooting guide is comprehensive

**Files to Create/Modify:**
- `docs/knowledge-graph-api.md`
- `docs/neo4j-deployment.md`
- `docs/troubleshooting-neo4j.md`

## Risk Mitigation Tasks

### Task R.1: Backup and Recovery
**Priority**: High  
**Estimated Time**: 3 hours  

**Subtasks:**
- [ ] Set up automated EBS snapshots
- [ ] Create Neo4j database backup scripts
- [ ] Test recovery procedures
- [ ] Document backup/recovery process

### Task R.2: Performance Monitoring
**Priority**: Medium  
**Estimated Time**: 2 hours  

**Subtasks:**
- [ ] Set up Neo4j performance metrics
- [ ] Configure memory and CPU monitoring
- [ ] Set up query performance tracking
- [ ] Create performance dashboards

### Task R.3: Security Hardening
**Priority**: High  
**Estimated Time**: 2 hours  

**Subtasks:**
- [ ] Review and harden Neo4j configuration
- [ ] Implement connection encryption
- [ ] Set up audit logging
- [ ] Review IAM permissions

## Success Metrics

### Technical Metrics
- [ ] Neo4j instance uptime >99%
- [ ] API response time <500ms for basic queries
- [ ] Knowledge graph extraction success rate >90%
- [ ] Zero security vulnerabilities

### Functional Metrics
- [ ] All health checks pass
- [ ] Document processing creates meaningful graphs
- [ ] API endpoints return expected results
- [ ] Integration with existing features works

### Business Metrics
- [ ] Deployment cost increase <$50/month
- [ ] No impact on existing application performance
- [ ] Knowledge graph features enhance user experience

## Timeline Summary

**Week 1**: Infrastructure setup and basic connectivity
**Week 2**: Application integration and API implementation  
**Week 3**: Document processing and advanced features
**Week 4**: Testing, deployment, and documentation

**Total Estimated Time**: 60-70 hours
**Target Completion**: 4 weeks from start