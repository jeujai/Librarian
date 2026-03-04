# Deployment Procedures

## Overview

This document provides comprehensive deployment procedures for the Multimodal Librarian system, covering development, staging, and production environments. These procedures ensure consistent, reliable deployments with proper validation and rollback capabilities.

## Prerequisites

### System Requirements
- Docker and Docker Compose installed
- Python 3.9+ with virtual environment support
- Access to required cloud services (AWS, database instances)
- Proper environment variables and secrets configured

### Access Requirements
- Repository access with appropriate permissions
- Cloud infrastructure access (AWS console, CLI configured)
- Database access credentials
- Monitoring and logging system access

## Environment Overview

### Development Environment
- **Purpose**: Local development and testing
- **Infrastructure**: Docker containers, local databases
- **Deployment Method**: Docker Compose
- **Validation**: Unit tests, integration tests

### Staging Environment
- **Purpose**: Pre-production testing and validation
- **Infrastructure**: Cloud-based, mirrors production
- **Deployment Method**: Automated CI/CD pipeline
- **Validation**: Full test suite, performance testing

### Production Environment
- **Purpose**: Live system serving users
- **Infrastructure**: High-availability cloud deployment
- **Deployment Method**: Blue-green deployment
- **Validation**: Health checks, smoke tests, monitoring

## Deployment Procedures

### 1. Development Deployment

#### Quick Start
```bash
# Clone repository
git clone <repository-url>
cd multimodal-librarian

# Set up environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with appropriate values

# Start services
docker-compose up -d

# Run database migrations
python src/multimodal_librarian/database/init_db.py

# Verify deployment
python -m pytest tests/ -v
```

#### Detailed Steps

1. **Environment Setup**
   ```bash
   # Create and activate virtual environment
   python -m venv venv
   source venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # For development tools
   ```

2. **Configuration**
   ```bash
   # Copy environment template
   cp .env.example .env
   
   # Required environment variables:
   # - DATABASE_URL
   # - VECTOR_STORE_URL
   # - AI_API_KEYS
   # - LOG_LEVEL
   ```

3. **Service Startup**
   ```bash
   # Start infrastructure services
   docker-compose up -d postgres redis milvus
   
   # Wait for services to be ready
   ./scripts/wait-for-services.sh
   
   # Initialize database
   python src/multimodal_librarian/database/init_db.py
   
   # Start application
   python src/multimodal_librarian/main.py
   ```

4. **Validation**
   ```bash
   # Run health checks
   curl http://localhost:8000/health
   
   # Run test suite
   python -m pytest tests/ -v --cov=src/
   
   # Test key functionality
   python scripts/test-core-functionality-validation.py
   ```

### 2. Staging Deployment

#### Automated Pipeline
The staging deployment is triggered automatically on merge to the `develop` branch.

#### Manual Deployment
```bash
# Ensure you're on the correct branch
git checkout develop
git pull origin develop

# Build and tag image
docker build -t multimodal-librarian:staging .
docker tag multimodal-librarian:staging <registry>/multimodal-librarian:staging

# Push to registry
docker push <registry>/multimodal-librarian:staging

# Deploy to staging
./scripts/deploy-to-staging.sh

# Run validation tests
./scripts/test-staging-deployment.py
```

#### Staging Validation Checklist
- [ ] All services start successfully
- [ ] Database migrations applied
- [ ] Health checks pass
- [ ] Integration tests pass
- [ ] Performance benchmarks meet targets
- [ ] Security scans pass
- [ ] Load testing completes successfully

### 3. Production Deployment

#### Pre-Deployment Checklist
- [ ] Staging deployment validated
- [ ] All tests passing
- [ ] Performance benchmarks met
- [ ] Security review completed
- [ ] Database backup created
- [ ] Rollback plan prepared
- [ ] Monitoring alerts configured
- [ ] Team notified of deployment

#### Blue-Green Deployment Process

1. **Preparation**
   ```bash
   # Create deployment branch
   git checkout main
   git pull origin main
   git checkout -b deployment/$(date +%Y%m%d-%H%M%S)
   
   # Build production image
   docker build -t multimodal-librarian:$(git rev-parse --short HEAD) .
   docker tag multimodal-librarian:$(git rev-parse --short HEAD) <registry>/multimodal-librarian:latest
   
   # Push to registry
   docker push <registry>/multimodal-librarian:latest
   ```

2. **Deploy to Green Environment**
   ```bash
   # Deploy to inactive environment
   ./scripts/deploy-to-production.sh --environment=green
   
   # Wait for deployment to complete
   ./scripts/wait-for-deployment.sh --environment=green
   ```

3. **Validation**
   ```bash
   # Run health checks on green environment
   ./scripts/validate-production-deployment.py --environment=green
   
   # Run smoke tests
   ./scripts/test-production-deployment.py --environment=green --smoke-tests
   
   # Performance validation
   ./scripts/test-production-deployment.py --environment=green --performance-tests
   ```

4. **Traffic Switch**
   ```bash
   # Switch traffic to green environment
   ./scripts/switch-blue-green-traffic.py --to=green
   
   # Monitor for 5 minutes
   ./scripts/monitor-deployment.py --duration=300
   ```

5. **Post-Deployment Validation**
   ```bash
   # Full system validation
   ./scripts/test-production-deployment.py --full-suite
   
   # Monitor key metrics
   ./scripts/monitor-deployment.py --duration=1800  # 30 minutes
   ```

#### Rollback Procedure
If issues are detected during or after deployment:

```bash
# Immediate rollback
./scripts/emergency-rollback.sh

# Or controlled rollback
./scripts/switch-blue-green-traffic.py --to=blue

# Verify rollback
./scripts/validate-production-deployment.py --environment=blue
```

## Database Migrations

### Development
```bash
# Create new migration
python src/multimodal_librarian/database/migrations.py create --name="add_new_feature"

# Apply migrations
python src/multimodal_librarian/database/migrations.py migrate

# Rollback if needed
python src/multimodal_librarian/database/migrations.py rollback --steps=1
```

### Production
```bash
# Backup database before migration
./scripts/backup-database.sh --environment=production

# Apply migrations with validation
python src/multimodal_librarian/database/migrations.py migrate --validate --dry-run
python src/multimodal_librarian/database/migrations.py migrate --validate

# Verify migration success
./scripts/validate-database-migration.py
```

## Configuration Management

### Environment Variables
```bash
# Required for all environments
DATABASE_URL=postgresql://user:pass@host:port/db
VECTOR_STORE_URL=http://milvus:19530
LOG_LEVEL=INFO

# Production-specific
ENVIRONMENT=production
DEBUG=false
SENTRY_DSN=https://...
MONITORING_ENABLED=true

# Security
JWT_SECRET_KEY=<secure-random-key>
ENCRYPTION_KEY=<secure-encryption-key>
```

### Secrets Management
- Use AWS Secrets Manager for production
- Use environment variables for development
- Never commit secrets to version control
- Rotate secrets regularly

## Monitoring and Alerting

### Health Check Endpoints
- `/health` - Overall system health
- `/health/startup` - Startup sequence status
- `/health/search` - Search service availability
- `/health/vector-store` - Vector database connectivity
- `/health/ai-services` - AI service responsiveness

### Key Metrics to Monitor
- Response time (< 500ms for search operations)
- Error rate (< 0.1%)
- Memory usage (< 2GB baseline)
- CPU utilization (< 80%)
- Database connection pool usage
- Cache hit rate (> 70%)

### Alert Thresholds
- **Critical**: Service down, error rate > 5%
- **Warning**: High latency, low cache hit rate
- **Info**: Deployment events, configuration changes

## Troubleshooting

### Common Issues

#### Service Won't Start
1. Check environment variables
2. Verify database connectivity
3. Check port availability
4. Review application logs

#### High Memory Usage
1. Check for memory leaks in logs
2. Review cache configuration
3. Monitor garbage collection
4. Scale resources if needed

#### Search Performance Issues
1. Check vector store connectivity
2. Review search query complexity
3. Monitor cache hit rates
4. Consider fallback service activation

#### Database Connection Issues
1. Verify connection string
2. Check network connectivity
3. Review connection pool settings
4. Monitor database server health

### Log Locations
- Application logs: `/var/log/multimodal-librarian/app.log`
- Error logs: `/var/log/multimodal-librarian/error.log`
- Access logs: `/var/log/multimodal-librarian/access.log`
- System logs: `/var/log/syslog`

## Security Considerations

### Deployment Security
- Use secure communication (HTTPS/TLS)
- Validate all inputs and configurations
- Implement proper authentication and authorization
- Regular security scans and updates

### Access Control
- Limit deployment access to authorized personnel
- Use role-based access control (RBAC)
- Implement audit logging for all deployment activities
- Regular access review and cleanup

## Backup and Recovery

### Backup Procedures
```bash
# Database backup
./scripts/backup-database.sh --environment=production

# Configuration backup
./scripts/backup-configuration.sh

# Application data backup
./scripts/backup-application-data.sh
```

### Recovery Procedures
```bash
# Database recovery
./scripts/restore-database.sh --backup-file=<backup-file>

# Full system recovery
./scripts/disaster-recovery.py --restore-point=<timestamp>
```

## Performance Optimization

### Pre-Deployment Optimization
- Run performance tests in staging
- Optimize database queries
- Configure caching appropriately
- Review resource allocation

### Post-Deployment Monitoring
- Monitor key performance metrics
- Set up automated scaling rules
- Regular performance reviews
- Capacity planning updates

## Compliance and Auditing

### Deployment Auditing
- Log all deployment activities
- Track configuration changes
- Monitor access patterns
- Regular compliance reviews

### Documentation Updates
- Update deployment logs
- Maintain configuration documentation
- Review and update procedures
- Training material updates

## Emergency Procedures

### Service Outage
1. Assess impact and scope
2. Implement immediate mitigation
3. Communicate with stakeholders
4. Execute recovery procedures
5. Conduct post-incident review

### Security Incident
1. Isolate affected systems
2. Assess security impact
3. Implement containment measures
4. Execute incident response plan
5. Document and report incident

### Data Loss
1. Stop all write operations
2. Assess data loss scope
3. Implement recovery procedures
4. Validate data integrity
5. Resume normal operations

## Contact Information

### Escalation Contacts
- **Primary On-Call**: [Contact Information]
- **Secondary On-Call**: [Contact Information]
- **Engineering Manager**: [Contact Information]
- **Security Team**: [Contact Information]

### External Contacts
- **Cloud Provider Support**: [Contact Information]
- **Database Support**: [Contact Information]
- **Monitoring Service**: [Contact Information]

---

**Document Version**: 1.0  
**Last Updated**: $(date)  
**Next Review**: $(date -d "+3 months")