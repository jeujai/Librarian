# AWS Deployment Architecture Design

## Overview

This document outlines the technical architecture for deploying the Multimodal Librarian system to Amazon Web Services (AWS). The design emphasizes scalability, security, high availability, and cost optimization while leveraging the existing Docker infrastructure and maintaining full compatibility with the current system including the multimedia chat interface, ML training APIs, and adaptive chunking framework.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    AWS Cloud                                       │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                              VPC (10.0.0.0/16)                              │  │
│  │                                                                               │  │
│  │  ┌─────────────────┐                           ┌─────────────────┐          │  │
│  │  │   Public Subnet │                           │   Public Subnet │          │  │
│  │  │   (10.0.1.0/24) │                           │   (10.0.2.0/24) │          │  │
│  │  │       AZ-A      │                           │       AZ-B      │          │  │
│  │  │                 │                           │                 │          │  │
│  │  │  ┌─────────────┐│                           │┌─────────────┐  │          │  │
│  │  │  │     ALB     ││                           ││   NAT GW    │  │          │  │
│  │  │  │ WebSocket   ││                           │└─────────────┘  │          │  │
│  │  │  │  Support    ││                           │                 │          │  │
│  │  │  └─────────────┘│                           │                 │          │  │
│  │  └─────────────────┘                           └─────────────────┘          │  │
│  │                                                                               │  │
│  │  ┌─────────────────┐                           ┌─────────────────┐          │  │
│  │  │  Private Subnet │                           │  Private Subnet │          │  │
│  │  │  (10.0.3.0/24)  │                           │  (10.0.4.0/24)  │          │  │
│  │  │       AZ-A      │                           │       AZ-B      │          │  │
│  │  │                 │                           │                 │          │  │
│  │  │ ┌─────────────┐ │                           │ ┌─────────────┐ │          │  │
│  │  │ │ ECS Tasks   │ │                           │ │ ECS Tasks   │ │          │  │
│  │  │ │ - Web App   │ │                           │ │ - Web App   │ │          │  │
│  │  │ │ - Chat API  │ │                           │ │ - Chat API  │ │          │  │
│  │  │ │ - ML APIs   │ │                           │ │ - ML APIs   │ │          │  │
│  │  │ │ - Workers   │ │                           │ │ - Workers   │ │          │  │
│  │  │ │ - Milvus    │ │                           │ │ - Milvus    │ │          │  │
│  │  │ └─────────────┘ │                           │ └─────────────┘ │          │  │
│  │  └─────────────────┘                           └─────────────────┘          │  │
│  │                                                                               │  │
│  │  ┌─────────────────┐                           ┌─────────────────┐          │  │
│  │  │   DB Subnet     │                           │   DB Subnet     │          │  │
│  │  │  (10.0.5.0/24)  │                           │  (10.0.6.0/24)  │          │  │
│  │  │       AZ-A      │                           │       AZ-B      │          │  │
│  │  │                 │                           │                 │          │  │
│  │  │ ┌─────────────┐ │                           │ ┌─────────────┐ │          │  │
│  │  │ │ RDS Primary │ │                           │ │RDS Secondary│ │          │  │
│  │  │ │ PostgreSQL  │ │                           │ │ (Standby)   │ │          │  │
│  │  │ └─────────────┘ │                           │ └─────────────┘ │          │  │
│  │  │ ┌─────────────┐ │                           │ ┌─────────────┐ │          │  │
│  │  │ │   Neo4j     │ │                           │ │ElastiCache  │ │          │  │
│  │  │ │  Cluster    │ │                           │ │   Redis     │ │          │  │
│  │  │ └─────────────┘ │                           │ └─────────────┘ │          │  │
│  │  └─────────────────┘                           └─────────────────┘          │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐  │
│  │                            External Services                                  │  │
│  │                                                                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │  │
│  │  │     S3      │  │ CloudFront  │  │   Route53   │  │    WAF      │        │  │
│  │  │   Buckets   │  │     CDN     │  │     DNS     │  │ Protection  │        │  │
│  │  │ - Documents │  │ - Static    │  │             │  │             │        │  │
│  │  │ - Media     │  │ - Media     │  │             │  │             │        │  │
│  │  │ - Exports   │  │ - Assets    │  │             │  │             │        │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │  │
│  │                                                                               │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │  │
│  │  │ CloudWatch  │  │   X-Ray     │  │   Secrets   │  │ Certificate │        │  │
│  │  │ Monitoring  │  │   Tracing   │  │   Manager   │  │   Manager   │        │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Networking Layer

**VPC Configuration (Cost-Optimized)**
- **CIDR Block**: 10.0.0.0/16 (65,536 IP addresses)
- **Availability Zones**: Single AZ for cost savings
- **Subnets**:
  - Public Subnet: 10.0.1.0/24 (ALB, NAT Gateway)
  - Private Subnet: 10.0.3.0/24 (Application tier)
  - Database Subnet: 10.0.5.0/24 (Database tier)

**Security Groups (Simplified)**
- **ALB Security Group**: HTTP/HTTPS from internet (0.0.0.0/0)
- **Application Security Group**: HTTP from ALB only
- **Database Security Group**: PostgreSQL/Neo4j/Redis from application tier only

### 2. Compute Layer

**Container Orchestration: AWS ECS Fargate (Cost-Optimized)**
- **Cluster**: Single-AZ ECS cluster with Fargate launch type
- **Services** (minimal configuration):
  - **Web Application Service**: 1-2 tasks (FastAPI with chat interface)
  - **Background Workers**: 1 task (PDF processing, chunking)
  - **Milvus Service**: 1 task (vector database)
  - **Milvus Support**: Single etcd and MinIO tasks

**Task Definitions** (cost-optimized)
```yaml
Web Application:
  CPU: 0.5 vCPU (512 units)
  Memory: 1 GB (1024 MB)
  Port: 8000
  Health Check: /health
  Environment: Development settings

Background Workers:
  CPU: 0.5 vCPU (512 units)
  Memory: 2 GB (2048 MB)
  No exposed ports
  Optimized for basic PDF processing

Milvus Vector Database:
  CPU: 0.5 vCPU (512 units)
  Memory: 2 GB (2048 MB)
  Ports: 19530, 9091
  Basic storage configuration
```

**Scaling Configuration (Manual)**
- **Manual Scaling**: No auto-scaling to control costs
- **Min Capacity**: 1 task per service
- **Max Capacity**: 2 tasks for web service, 1 for others
- **Scaling**: Manual adjustment based on usage

### 3. Load Balancing

**Application Load Balancer (ALB)**
- **Scheme**: Internet-facing
- **Listeners**:
  - HTTP (80) → Redirect to HTTPS
  - HTTPS (443) → Target Groups
- **WebSocket Support**: Enabled for chat interface
- **Target Groups**:
  - Web Application: Health check on /health
  - API Endpoints: Health check on /api/health
  - WebSocket: Sticky sessions enabled for chat

**Routing Rules** (based on existing API structure)
```
/api/chat/* → Chat API Target Group (WebSocket support)
/api/ml-training/* → ML Training API Target Group
/api/export/* → Export API Target Group
/api/query/* → Query API Target Group
/ws/* → WebSocket Service Target Group
/static/* → CloudFront CDN
/* → Web Application Target Group
```

### 4. Database Layer

**Primary Database: AWS RDS PostgreSQL (Cost-Optimized)**
- **Engine**: PostgreSQL 15.x (matching existing setup)
- **Instance Class**: db.t3.micro (1 vCPU, 1 GB RAM) - Free Tier eligible
- **Storage**: 20 GB GP2 SSD (Free Tier eligible)
- **Single-AZ**: No Multi-AZ for cost savings
- **Backup**: 7-day retention, automated backups
- **Encryption**: At rest only (in transit optional for cost)
- **Schema**: Use existing `init_db.sql` and migrations

**Knowledge Graph: Neo4j on Single EC2**
- **Instance Type**: t3.small (2 vCPU, 2 GB RAM)
- **Storage**: 50 GB GP2 SSD
- **Deployment**: Single instance (no clustering for cost)
- **Plugins**: APOC only (skip Graph Data Science for cost)
- **Backup**: Weekly snapshots to S3
- **Security**: Private subnet, basic security group

**Vector Database: Milvus on Single ECS Task**
- **Deployment**: Single ECS Fargate task
- **Supporting Services**: Single etcd and MinIO tasks
- **Storage**: EFS Basic (no provisioned throughput)
- **Configuration**: Minimal Milvus settings
- **Scaling**: Manual scaling only

**Caching: ElastiCache Redis (Minimal)**
- **Node Type**: cache.t3.micro (1 vCPU, 0.5 GB RAM)
- **Deployment**: Single node (no clustering)
- **Backup**: No snapshots for cost savings
- **Encryption**: At rest only

### 5. Storage Layer

**Document Storage: Amazon S3 (Cost-Optimized)**
- **Buckets** (consolidated for cost):
  - `multimodal-librarian-learning-prod`: All files (uploads, media, exports, logs)

**Bucket Configuration (Cost-Optimized)**
- **Versioning**: Disabled to save storage costs
- **Encryption**: Server-side encryption (free)
- **Lifecycle Policies**:
  - All files: Transition to IA after 30 days, delete after 90 days
  - Logs: Delete after 7 days

**Content Delivery: Amazon CloudFront (Basic)**
- **Origins**: S3 bucket only (no ALB origin for cost)
- **Caching Behavior**:
  - Static assets: Cache for 1 month
  - No custom behaviors for cost savings
- **Security**: Basic Origin Access Control (OAC)

### 6. Security Layer

**Web Application Firewall (WAF)**
- **Managed Rules**:
  - AWS Core Rule Set
  - Known Bad Inputs
  - SQL Injection Protection
  - XSS Protection
- **Custom Rules**:
  - Rate limiting: 1000 requests per 5 minutes per IP
  - File upload size limits (100MB for PDFs)
  - API endpoint protection

**SSL/TLS Certificates**
- **Provider**: AWS Certificate Manager
- **Validation**: DNS validation
- **Domains**: Primary domain + wildcard subdomain
- **Renewal**: Automatic

**Secrets Management**
- **AWS Secrets Manager**: Database credentials, API keys
  - Gemini API key (existing)
  - OpenAI API key (existing)
  - Google API key (existing)
  - Database passwords
  - Encryption keys
- **AWS Systems Manager Parameter Store**: Configuration values
- **Rotation**: Automatic for database credentials
- **Access**: IAM role-based, least privilege

### 7. Monitoring and Logging

**Amazon CloudWatch**
- **Metrics**:
  - Application metrics (custom from existing monitoring)
  - ML training metrics (from existing ML monitor)
  - Chunking framework performance
  - Infrastructure metrics (CPU, memory, network)
  - Database metrics (connections, queries)
  - Vector database metrics (search latency, indexing)

**Log Groups** (based on existing log structure)
- `/aws/ecs/multimodal-librarian/web`
- `/aws/ecs/multimodal-librarian/api`
- `/aws/ecs/multimodal-librarian/ml-training`
- `/aws/ecs/multimodal-librarian/workers`
- `/aws/ecs/multimodal-librarian/milvus`
- `/aws/rds/postgresql/error`
- `/aws/ec2/neo4j`

**AWS X-Ray**
- **Tracing**: End-to-end request tracing
- **Service Map**: Visual representation of service dependencies
- **Performance Analysis**: Identify bottlenecks in ML training and chunking
- **Integration**: With existing FastAPI application

**Alerting**
- **Critical Alerts**: Service down, database connection failures, ML training failures
- **Warning Alerts**: High CPU, memory usage, error rates, slow chunking
- **Cost Alerts**: Budget thresholds exceeded
- **Custom Alerts**: ML training completion, large PDF processing

### 8. CI/CD Pipeline

**GitHub Actions Workflow** (extending existing structure)
```yaml
Triggers:
  - Push to main branch
  - Pull request to main
  - Manual dispatch

Stages:
  1. Test: Run all 151 existing tests
  2. Build: Build Docker images using existing Dockerfile
  3. Security Scan: Container vulnerability scanning
  4. Deploy to Staging: Deploy to staging environment
  5. Integration Tests: Run AWS-specific integration tests
  6. ML Training Tests: Validate ML APIs and chunking framework
  7. Deploy to Production: Blue-green deployment
  8. Health Check: Verify all services including chat interface
  9. Rollback: Automatic rollback on failure
```

**Deployment Strategy**
- **Blue-Green Deployment**: Zero-downtime deployments
- **Health Checks**: Comprehensive health validation including ML services
- **Rollback**: Automatic rollback on health check failure
- **Notifications**: Slack/email notifications for deployments

## Data Flow Architecture

### 1. Document Processing Flow (Enhanced)
```
User Upload → S3 → Lambda Trigger → SQS Queue → ECS Worker → 
PDF Processing → Multi-Level Chunking Framework → 
Vector Embeddings → Milvus + PostgreSQL + Neo4j
```

### 2. Chat Interface Flow
```
User Message → ALB → WebSocket Service → 
Conversation Manager → Context Processor → 
Knowledge Integration (Vector + Graph) → 
Response Generation → WebSocket → User
```

### 3. ML Training Flow
```
Training Request → ALB → ML Training API → 
Knowledge Stream Access → Chunk Sequences → 
RL Training Data → Training Process → 
Model Updates → Response
```

### 4. Query Processing Flow
```
User Query → ALB → API Service → 
Query Processor → Vector Search (Milvus) + 
Knowledge Graph (Neo4j) + Database (PostgreSQL) → 
Response Synthesizer → Multimedia Generator → User
```

## Scalability Design

### Horizontal Scaling
- **Application Tier**: Auto-scaling ECS services
- **Database Tier**: Read replicas for PostgreSQL
- **Vector Database**: Milvus cluster scaling
- **Cache Tier**: Redis cluster with multiple nodes
- **Storage Tier**: S3 unlimited scalability

### Vertical Scaling
- **Database**: Upgrade instance classes as needed
- **Application**: Increase task CPU/memory allocation
- **ML Training**: GPU instances for intensive workloads
- **Cache**: Upgrade node types for more memory

### Performance Optimization
- **Connection Pooling**: PgBouncer for PostgreSQL
- **Caching Strategy**: Multi-level caching (Redis, CloudFront)
- **Database Optimization**: Proper indexing, query optimization
- **Vector Optimization**: Milvus index tuning for search performance
- **CDN**: Global content delivery for static assets and media

## Integration with Existing System

### Docker Compatibility
- **Base Images**: Use existing Dockerfile as foundation
- **Environment Variables**: Migrate from docker-compose.yml
- **Service Dependencies**: Maintain existing service relationships
- **Health Checks**: Use existing health check endpoints

### Database Migration
- **PostgreSQL**: Use existing schema and init scripts
- **Milvus**: Migrate existing collections and indexes
- **Neo4j**: Export/import existing graph data
- **Redis**: Maintain existing caching patterns

### Application Integration
- **API Endpoints**: Preserve all existing endpoints
- **WebSocket Support**: Maintain chat interface functionality
- **ML Training**: Preserve existing ML training APIs
- **Export Engine**: Maintain all export formats
- **Chunking Framework**: Preserve adaptive chunking capabilities

## Security Architecture

### Network Security
- **VPC**: Isolated network environment
- **Security Groups**: Stateful firewall rules
- **NACLs**: Additional network-level security
- **VPC Endpoints**: Private connectivity to AWS services

### Application Security
- **WAF**: Web application firewall protection
- **IAM**: Role-based access control
- **Encryption**: Data at rest and in transit
- **Secrets Management**: Centralized secret storage
- **Audit Logging**: Integration with existing audit system

### Compliance
- **Data Encryption**: AES-256 encryption
- **Access Logging**: CloudTrail for audit trails
- **Monitoring**: Real-time security monitoring
- **Backup**: Encrypted backups with retention policies

## Cost Optimization

### Compute Costs
- **Fargate**: Pay only for running tasks
- **Auto Scaling**: Scale down during low usage
- **Spot Instances**: For batch processing workloads
- **Reserved Instances**: For predictable ML training workloads

### Storage Costs
- **S3 Intelligent Tiering**: Automatic cost optimization
- **Lifecycle Policies**: Move old data to cheaper storage
- **CloudFront**: Reduce origin requests
- **EFS**: Optimized storage for Milvus data

### Database Costs
- **Right-sizing**: Monitor and adjust instance sizes
- **Read Replicas**: Only when needed for scaling
- **Backup Optimization**: Optimize retention periods

## Disaster Recovery

### Backup Strategy
- **RDS**: Automated backups with 7-day retention
- **S3**: Cross-region replication for critical data
- **Neo4j**: Daily snapshots to S3
- **Milvus**: EFS snapshots and S3 backup
- **Configuration**: Infrastructure as Code in Git

### Recovery Procedures
- **RTO**: 4 hours (Recovery Time Objective)
- **RPO**: 1 hour (Recovery Point Objective)
- **Multi-Region**: Standby environment in different region
- **Automation**: Automated recovery procedures

## Implementation Phases

### Phase 1: Foundation (Week 1)
- VPC and networking setup
- Security groups and IAM roles
- RDS PostgreSQL database
- S3 bucket configuration

### Phase 2: Application (Week 2)
- ECS cluster setup
- Container deployment using existing Docker images
- Load balancer configuration with WebSocket support
- SSL certificate setup

### Phase 3: Enhancement (Week 3)
- Milvus and Neo4j setup
- Monitoring and logging integration
- Auto-scaling configuration
- CDN setup for media delivery

### Phase 4: Production (Week 4)
- Security hardening
- Performance optimization
- Backup and DR setup
- Documentation and handover

## Success Metrics

### Performance
- **Response Time**: < 5 seconds for 95% of requests (acceptable for learning)
- **Availability**: 95% uptime (learning environment)
- **Throughput**: 10-20 concurrent users
- **Scalability**: Manual scaling from 1 to 3 instances
- **ML Training**: Basic training functionality operational

### Cost
- **Monthly Cost**: Target $50-200 for learning deployment
- **Cost per User**: < $5 per active user per month
- **Optimization**: 80% cost reduction through simplified architecture

### Security
- **Vulnerabilities**: No critical vulnerabilities (basic security)
- **Compliance**: Basic security practices for learning
- **Encryption**: Data encrypted at rest (basic level)
- **Access Control**: Simple IAM roles and security groups

### Functionality
- **Test Coverage**: All 151 existing tests pass
- **Chat Interface**: Full WebSocket functionality maintained
- **ML Training**: All ML APIs operational
- **Export Engine**: All export formats working
- **Chunking Framework**: Adaptive chunking operational

This architecture provides a robust, scalable, and secure foundation for deploying the Multimodal Librarian system to AWS while maintaining full compatibility with existing functionality and ensuring optimal performance for the multimedia chat interface, ML training capabilities, and adaptive chunking framework.