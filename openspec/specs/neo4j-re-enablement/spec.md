## Purpose

Re-enable Neo4j knowledge graph functionality for the multimodal-librarian-full-ml deployment. Neo4j was temporarily disabled during deployment fixes but needs to be restored to provide full knowledge graph capabilities.

## Requirements

### Requirement: US-1: Neo4j Infrastructure Setup

The system SHALL implement us-1: neo4j infrastructure setup as described in the requirements.

#### Scenario: Neo4j instance deployed on AWS EC2 with appropriate instance

- **THEN** Neo4j instance deployed on AWS EC2 with appropriate instance type

#### Scenario: Security groups configured for secure access from ECS tasks

- **THEN** Security groups configured for secure access from ECS tasks

#### Scenario: Backup and monitoring configured

- **THEN** Backup and monitoring configured

#### Scenario: Neo4j accessible from full-ml ECS cluster

- **THEN** Neo4j accessible from full-ml ECS cluster

#### Scenario: Connection credentials stored in AWS Secrets Manager

- **THEN** Connection credentials stored in AWS Secrets Manager

### Requirement: US-2: Application Integration

The system SHALL implement us-2: application integration as described in the requirements.

#### Scenario: Neo4j client integrated into main_minimal.py

- **THEN** Neo4j client integrated into main_minimal.py

#### Scenario: Connection using credentials from `multimodal-librarian/full

- **THEN** Connection using credentials from `multimodal-librarian/full-ml/neo4j` secret

#### Scenario: Health check endpoint `/test/neo4j` returns connection statu

- **THEN** Health check endpoint `/test/neo4j` returns connection status

#### Scenario: Error handling for Neo4j connection failures

- **THEN** Error handling for Neo4j connection failures

### Requirement: US-3: Knowledge Graph API Endpoints

The system SHALL implement us-3: knowledge graph api endpoints as described in the requirements.

#### Scenario: `/api/knowledge-graph/create` endpoint for creating nodes/re

- **THEN** `/api/knowledge-graph/create` endpoint for creating nodes/relationships

#### Scenario: `/api/knowledge-graph/query` endpoint for Cypher queries

- **THEN** `/api/knowledge-graph/query` endpoint for Cypher queries

#### Scenario: `/api/knowledge-graph/search` endpoint for semantic search

- **THEN** `/api/knowledge-graph/search` endpoint for semantic search

#### Scenario: Proper error handling and validation

- **THEN** Proper error handling and validation

#### Scenario: API documentation in OpenAPI/Swagger

- **THEN** API documentation in OpenAPI/Swagger

### Requirement: US-4: Knowledge Graph Processing

The system SHALL implement us-4: knowledge graph processing as described in the requirements.

#### Scenario: Document upload triggers knowledge graph extraction

- **THEN** Document upload triggers knowledge graph extraction

#### Scenario: Entity recognition and relationship extraction

- **THEN** Entity recognition and relationship extraction

#### Scenario: Integration with existing PDF processing pipeline

- **THEN** Integration with existing PDF processing pipeline

#### Scenario: Knowledge graph visualization capabilities

- **THEN** Knowledge graph visualization capabilities
