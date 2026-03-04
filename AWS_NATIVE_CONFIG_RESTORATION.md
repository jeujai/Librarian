# AWS-Native Configuration Restoration

**Date**: January 16, 2026  
**Issue**: Task definition regression from AWS-native to development configuration  
**Resolution**: Created new task definition revision 42 with correct AWS-native endpoints

## Problem Summary

Task definition revision 41 was deployed with **development/localhost configuration** instead of the **AWS-native production configuration**. This caused the application to fail because it was trying to connect to:

- `localhost:5432` (PostgreSQL) - doesn't exist in Fargate
- `localhost:19530` (Milvus) - doesn't exist in Fargate  
- `localhost:6379` (Redis) - doesn't exist in Fargate
- Local Neo4j instance - doesn't exist in Fargate

## Root Cause

The task definition was created without the necessary environment variables that point to the AWS-managed services (Neptune, OpenSearch, RDS, ElastiCache).

## Solution Applied

Created task definition **revision 42** with the correct AWS-native configuration:

### AWS-Native Service Endpoints

| Service | Endpoint | Purpose |
|---------|----------|---------|
| **Neptune** | `multimodal-lib-prod-neptune.cluster-cq1iiac2gfkf.us-east-1.neptune.amazonaws.com:8182` | Graph database (replaces Neo4j) |
| **OpenSearch** | `vpc-multimodal-lib-prod-search-2mjsemd5qwcuj3ezeltxxmwkrq.us-east-1.es.amazonaws.com:443` | Vector search (replaces Milvus) |
| **RDS PostgreSQL** | `multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com:5432` | Relational database |
| **ElastiCache Redis** | `master.multimodal-lib-prod-redis.znjbcw.use1.cache.amazonaws.com:6379` | Caching layer |

### Environment Variables Added

```bash
# AWS-Native Mode
USE_AWS_NATIVE=true

# Neptune Configuration
NEPTUNE_CLUSTER_ENDPOINT=multimodal-lib-prod-neptune.cluster-cq1iiac2gfkf.us-east-1.neptune.amazonaws.com
NEPTUNE_PORT=8182

# OpenSearch Configuration  
OPENSEARCH_DOMAIN_ENDPOINT=https://vpc-multimodal-lib-prod-search-2mjsemd5qwcuj3ezeltxxmwkrq.us-east-1.es.amazonaws.com
OPENSEARCH_PORT=443

# RDS PostgreSQL Configuration
DATABASE_HOST=multimodallibrarianfullml-databasepostgresdatabase-ccjxkhsancro.cq1iiac2gfkf.us-east-1.rds.amazonaws.com
DATABASE_PORT=5432
DATABASE_NAME=multimodal_librarian
DATABASE_USER=postgres

# ElastiCache Redis Configuration
REDIS_HOST=master.multimodal-lib-prod-redis.znjbcw.use1.cache.amazonaws.com
REDIS_PORT=6379

# AWS Region
AWS_DEFAULT_REGION=us-east-1
AWS_REGION=us-east-1
```

### Secrets Configuration

```json
[
  {
    "name": "DATABASE_PASSWORD",
    "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/database-OxpSTB:password::"
  },
  {
    "name": "REDIS_PASSWORD",
    "valueFrom": "arn:aws:secretsmanager:us-east-1:591222106065:secret:multimodal-librarian/full-ml/redis-7UEzui:password::"
  }
]
```

## Deployment Status

- **Old Revision**: 41 (development config - FAILED)
- **New Revision**: 42 (AWS-native config - DEPLOYING)
- **Service**: multimodal-lib-prod-service
- **Cluster**: multimodal-lib-prod-cluster

## How to Prevent This in the Future

### 1. Always Use the Correct Base Revision

When creating new task definitions, always base them on a **known-good AWS-native revision**:

```bash
# Check which revision has AWS-native config
aws ecs describe-task-definition --task-definition multimodal-lib-prod-app:42 \
  --query 'taskDefinition.containerDefinitions[0].environment[?name==`USE_AWS_NATIVE`]'
```

### 2. Validate Before Deployment

Before deploying any new task definition, verify it has the required environment variables:

```bash
# Check for AWS-native configuration
aws ecs describe-task-definition --task-definition multimodal-lib-prod-app:XX \
  --query 'taskDefinition.containerDefinitions[0].environment[?contains(name, `NEPTUNE`) || contains(name, `OPENSEARCH`) || contains(name, `DATABASE_HOST`)]'
```

### 3. Use the Switch Script

The script `scripts/switch-to-aws-native-config.py` can be used to quickly restore AWS-native configuration:

```bash
python3 scripts/switch-to-aws-native-config.py
```

### 4. Document Configuration in Spec

The AWS-native configuration is documented in:
- `.kiro/specs/aws-native-database-implementation/design.md`
- `.kiro/specs/aws-native-database-implementation/requirements.md`

Always refer to these specs when making infrastructure changes.

## Monitoring the Deployment

### Check Service Status
```bash
aws ecs describe-services \
  --cluster multimodal-lib-prod-cluster \
  --services multimodal-lib-prod-service \
  --query 'services[0].deployments'
```

### Check Task Logs
```bash
aws logs tail /ecs/multimodal-lib-prod-app --follow
```

### Verify Health
Once deployed, check the health endpoint:
```bash
# Get ALB DNS name
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[?contains(LoadBalancerName, `multimodal`)].DNSName' \
  --output text

# Test health endpoint
curl http://<alb-dns>/api/health/simple
```

## Related Specs

- **AWS-Native Database Implementation**: `.kiro/specs/aws-native-database-implementation/`
- **AWS Production Deployment**: `.kiro/specs/aws-production-deployment/`
- **Shared Infrastructure Optimization**: `.kiro/specs/shared-infrastructure-optimization/`

## Cost Implications

The AWS-native configuration uses managed services with the following monthly costs:

- **Neptune (db.t3.medium)**: ~$165-230/month
- **OpenSearch (t3.small.search)**: ~$57-83/month
- **RDS PostgreSQL**: ~$50-100/month (depending on instance size)
- **ElastiCache Redis**: ~$30-50/month

**Total**: ~$302-463/month for fully managed, production-ready infrastructure.

## Next Steps

1. ✅ Task definition revision 42 created with AWS-native config
2. ⏳ Monitor deployment progress
3. ⏳ Verify application starts successfully
4. ⏳ Test database connectivity (Neptune, OpenSearch, RDS, Redis)
5. ⏳ Validate health checks pass
6. ⏳ Confirm application functionality

## Troubleshooting

If the deployment fails:

1. **Check CloudWatch Logs**: Look for connection errors
2. **Verify Security Groups**: Ensure ECS tasks can reach database endpoints
3. **Check IAM Permissions**: Verify task role has permissions for Neptune, OpenSearch, Secrets Manager
4. **Validate Secrets**: Ensure database passwords are correct in Secrets Manager
5. **Network Configuration**: Verify VPC, subnets, and routing tables

## References

- [AWS Neptune Documentation](https://docs.aws.amazon.com/neptune/)
- [AWS OpenSearch Documentation](https://docs.aws.amazon.com/opensearch-service/)
- [ECS Task Definition Parameters](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
